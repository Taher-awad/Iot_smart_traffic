import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// --- CONFIGURATION ---
const LANE_WIDTH = 3.5; // meters
const INTERSECTION_SIZE = 15;
const CAR_SPEED = 10; // units/sec
const GATEWAY_WS_URL = 'ws://10.169.151.54:8765'; // Target Pi IP

// --- GLOBALS ---
let scene, camera, renderer, controls;
let cars = [];
let trafficLights = []; // [Red, Green] mesh pairs for 4 lanes
let laneGreen = 0; // Current green lane (0-3)
let lastSwitchTime = 0;
const SWITCH_INTERVAL = 5000; // ms

// --- ASSETS ---
const textureLoader = new THREE.TextureLoader();
const grassTexture = textureLoader.load('./assets/grass.png');
grassTexture.wrapS = THREE.RepeatWrapping;
grassTexture.wrapT = THREE.RepeatWrapping;
grassTexture.repeat.set(10, 10);

const roadTexture = textureLoader.load('./assets/road.png');
roadTexture.wrapS = THREE.RepeatWrapping;
roadTexture.wrapT = THREE.RepeatWrapping;
roadTexture.repeat.set(1, 20);
roadTexture.rotation = Math.PI / 2;

const carTexture = textureLoader.load('./assets/car.png');

// --- WS ---
let wsInfo = null;

function publishWS(topic, payload) {
    if (wsInfo && wsInfo.readyState === WebSocket.OPEN) {
        wsInfo.send(JSON.stringify({
            type: "log_publish",
            topic: topic,
            payload: payload
        }));
    }
}

function logMQTT(topic, msg) {
    const statusDiv = document.getElementById('status');
    const logDiv = document.createElement('div');
    logDiv.style.fontFamily = 'monospace';
    logDiv.style.fontSize = '0.9em';
    logDiv.style.marginTop = '4px';
    logDiv.style.color = '#00ff00';
    logDiv.innerText = `> ${topic}: ${msg}`;

    // Add to top of status, keep limit
    statusDiv.appendChild(logDiv);
    while (statusDiv.children.length > 6) statusDiv.removeChild(statusDiv.children[0]);
}

function init() {
    // 1. Setup Scene
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x87CEEB); // Sky blue
    scene.fog = new THREE.Fog(0x87CEEB, 20, 100);

    // 2. Camera
    camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.set(30, 40, 30); // Higher angle
    camera.lookAt(0, 0, 0);

    // 3. Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.shadowMap.enabled = true;
    document.body.appendChild(renderer.domElement);

    // 4. Controls
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    // 5. Light
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(50, 50, 50);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 2048;
    dirLight.shadow.mapSize.height = 2048;
    scene.add(dirLight);

    // 6. Environment
    createGround();
    createRoads();
    createTrafficLights();

    // 7. Event Listeners
    window.addEventListener('resize', onWindowResize);
    document.getElementById('addCar0').addEventListener('click', () => spawnCar(0));
    document.getElementById('addCar1').addEventListener('click', () => spawnCar(1));
    document.getElementById('addCar2').addEventListener('click', () => spawnCar(2));
    document.getElementById('addCar3').addEventListener('click', () => spawnCar(3));
    document.getElementById('toggleCam').addEventListener('click', toggleCamera);

    // Start Loop
    lastSwitchTime = Date.now();
    connectWebSocket();
    animate();
}

// --- WEBSOCKET CONNECTION ---
function connectWebSocket() {
    logMQTT("system", "Connecting to Gateway WebSocket...");
    const ws = new WebSocket(GATEWAY_WS_URL);
    wsInfo = ws;

    ws.onopen = () => {
        logMQTT("system", "WebSocket CONNECTED to Gateway!");
        publishWS("traffic/INT_WEB/logs", "ONLINE");
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === "log") {
                logMQTT(msg.unit_id, msg.data);
                if (msg.data.includes("Green: Lane")) {
                    const l = parseInt(msg.data.split("Lane ")[1]);
                    if (!isNaN(l)) laneGreen = l; // Sync visual with real ESP
                }
            } else if (msg.type === "command") {
                logMQTT("AWS", `Override Lane ${msg.lane} for ${msg.duration}ms`);
                overrideActive = true;
                overrideLane = msg.lane;
                overrideEndTime = Date.now() + msg.duration;
            }
        } catch (e) { console.error(e); }
    };

    ws.onclose = () => {
        logMQTT("system", "WebSocket Closed. Retrying...");
        setTimeout(connectWebSocket, 3000);
    };
}

function createGround() {
    const geometry = new THREE.PlaneGeometry(200, 200);
    const material = new THREE.MeshStandardMaterial({ map: grassTexture });
    const ground = new THREE.Mesh(geometry, material);
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);
}

function createRoads() {
    // Road 1 (North-South)
    const roadMatV = new THREE.MeshStandardMaterial({ map: roadTexture });
    const road1 = new THREE.Mesh(new THREE.PlaneGeometry(LANE_WIDTH * 2, 200), roadMatV);
    road1.rotation.x = -Math.PI / 2;
    road1.position.y = 0.01;
    road1.receiveShadow = true;
    scene.add(road1);

    // Road 2 (East-West)
    const roadMatH = new THREE.MeshStandardMaterial({ map: roadTexture });
    const road2 = new THREE.Mesh(new THREE.PlaneGeometry(200, LANE_WIDTH * 2), roadMatH);
    road2.rotation.x = -Math.PI / 2;
    road2.position.y = 0.01;
    road2.receiveShadow = true;
    scene.add(road2);

    // Intersection Box
    const intersection = new THREE.Mesh(new THREE.PlaneGeometry(LANE_WIDTH * 2.1, LANE_WIDTH * 2.1), new THREE.MeshStandardMaterial({ color: 0x222222 }));
    intersection.rotation.x = -Math.PI / 2;
    intersection.position.y = 0.02;
    scene.add(intersection);
}

function createTrafficLights() {
    const positions = [
        { x: -5, z: -5, rot: Math.PI },      // Lane 0
        { x: 5, z: -5, rot: Math.PI / 2 },     // Lane 1
        { x: 5, z: 5, rot: 0 },              // Lane 2
        { x: -5, z: 5, rot: -Math.PI / 2 }     // Lane 3
    ];

    positions.forEach((pos, index) => {
        // Pole
        const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 5), new THREE.MeshStandardMaterial({ color: 0x888888 }));
        pole.position.set(pos.x, 2.5, pos.z);
        scene.add(pole);

        // Box
        const box = new THREE.Mesh(new THREE.BoxGeometry(1, 2, 1), new THREE.MeshStandardMaterial({ color: 0x111111 }));
        box.position.set(pos.x, 5, pos.z);
        box.rotation.y = pos.rot;
        scene.add(box);

        // Lights
        const redLight = new THREE.Mesh(new THREE.SphereGeometry(0.3), new THREE.MeshStandardMaterial({ color: 0x330000, emissive: 0x000000 }));
        redLight.position.set(0, 0.5, 0.55);
        box.add(redLight);

        const greenLight = new THREE.Mesh(new THREE.SphereGeometry(0.3), new THREE.MeshStandardMaterial({ color: 0x003300, emissive: 0x000000 }));
        greenLight.position.set(0, -0.5, 0.55);
        box.add(greenLight);

        trafficLights.push({ red: redLight, green: greenLight, box: box });
    });

    updateLights();
}

function spawnCar(lane) {
    // const lane = Math.floor(Math.random() * 4); // REMOVED random
    // Check Spawn Collision
    const spawnPos = { x: 0, z: 0 };
    if (lane === 0) { spawnPos.x = -1.75; spawnPos.z = -40; }
    if (lane === 1) { spawnPos.x = 40; spawnPos.z = -1.75; }
    if (lane === 2) { spawnPos.x = 1.75; spawnPos.z = 40; }
    if (lane === 3) { spawnPos.x = -40; spawnPos.z = 1.75; }

    const isSafe = !cars.some(c => {
        const dx = c.position.x - spawnPos.x;
        const dz = c.position.z - spawnPos.z;
        return Math.sqrt(dx * dx + dz * dz) < 8; // 8 meters clearance
    });

    if (!isSafe) {
        console.log("Spawn Blocked");
        return;
    }

    const car = new THREE.Group();

    const bodyMat = new THREE.MeshStandardMaterial({ map: carTexture });
    const body = new THREE.Mesh(new THREE.BoxGeometry(2, 1, 4), bodyMat);
    body.position.y = 0.5;
    body.castShadow = true;
    car.add(body);

    const cabin = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.7, 2), new THREE.MeshStandardMaterial({ color: 0x222222 }));
    cabin.position.y = 1.35;
    car.add(cabin);

    switch (lane) {
        case 0: // Moves +Z
            car.position.set(-1.75, 0, -40);
            car.rotation.y = 0;
            break;
        case 1: // Moves -X (West)
            car.position.set(40, 0, -1.75);
            car.rotation.y = -Math.PI / 2;
            break;
        case 2: // Moves -Z (North)
            car.position.set(1.75, 0, 40);
            car.rotation.y = Math.PI;
            break;
        case 3: // Moves +X (East)
            car.position.set(-40, 0, 1.75);
            car.rotation.y = Math.PI / 2;
            break;
    }

    car.userData = { lane: lane, speed: 0, waiting: false };
    cars.push(car);
    scene.add(car);
}

// === ESP32 LOGIC CORE ===
// === ESP32 LOGIC CORE ===
let isSwitching = false;
let switchTarget = 0;
let switchStartTime = 0;
// Override State
let overrideActive = false;
let overrideLane = 0;
let overrideEndTime = 0;

function updateLogic() {
    const now = Date.now();

    // 0. Handle Transition State (All Red)
    if (isSwitching) {
        if (now - switchStartTime >= 500) { // 0.5s Delay (Matches ESP32)
            laneGreen = switchTarget;
            isSwitching = false;
            lastSwitchTime = now;
            publishWS(`traffic/INT_WEB/logs`, `Green: Lane ${laneGreen}`);
            updateLights();
        }
        return; // Skip normal logic while switching
    }

    // 1. OVERRIDE MODE
    if (overrideActive) {
        if (laneGreen !== overrideLane) {
            // Force switch immediately (or via safety delay)
            // For sim simplicity, let's switch immediately or we can trigger switching
            if (!isSwitching) {
                laneGreen = overrideLane;
                updateLights();
                publishWS(`traffic/INT_WEB/logs`, `Override Active: Lane ${laneGreen}`);
            }
        }

        if (now > overrideEndTime) {
            overrideActive = false;
            logMQTT("system", "Override Ended. Resuming logic.");
            lastSwitchTime = now; // Reset timer
        }
        return; // Skip normal logic
    }

    const stopLineDist = 7;
    let laneStatus = [false, false, false, false];
    cars.forEach(c => {
        let dist = 999;
        if (c.userData.lane === 0 && c.position.z < -5) dist = Math.abs(c.position.z - (-5));
        if (c.userData.lane === 1 && c.position.x > 5) dist = Math.abs(c.position.x - 5);
        if (c.userData.lane === 2 && c.position.z > 5) dist = Math.abs(c.position.z - 5);
        if (c.userData.lane === 3 && c.position.x < -5) dist = Math.abs(c.position.x - (-5));

        if (dist <= stopLineDist) laneStatus[c.userData.lane] = true;
    });

    let currentLaneEmpty = !laneStatus[laneGreen];
    let triggered = false;
    let nextLane = laneGreen;

    // B. Smart Switch (Priority Mode)
    if (currentLaneEmpty) {
        for (let i = 1; i <= 3; i++) {
            let check = (laneGreen + i) % 4;
            if (laneStatus[check]) {
                const logMsg = `Priority Switch -> Lane ${check}`;
                logMQTT(`traffic/INT_WEB/logs`, logMsg);
                publishWS(`traffic/INT_WEB/logs`, logMsg);

                nextLane = check;
                triggered = true;
                break;
            }
        }
    }

    // C. Timeout (Cycle)
    if (!triggered && now - lastSwitchTime > SWITCH_INTERVAL) {
        let old = laneGreen;
        nextLane = (laneGreen + 1) % 4;
        triggered = true;

        const logMsg = `Timeout Switch: Lane ${old} -> ${nextLane}`;
        logMQTT(`traffic/INT_WEB/logs`, logMsg);
    }

    // Execute Switch with Delay
    if (triggered) {
        isSwitching = true;
        switchTarget = nextLane;
        switchStartTime = now;
        laneGreen = -1; // All Red
        updateLights();
    }

    // Release cars (only if green)
    if (laneGreen !== -1) {
        cars.forEach(c => {
            if (c.userData.lane === laneGreen) c.userData.waiting = false;
        });
    }
}

function updateLights() {
    trafficLights.forEach((tl, idx) => {
        if (idx === laneGreen) {
            tl.green.material.emissive.setHex(0x00ff00);
            tl.green.material.color.setHex(0x00ff00);
            tl.red.material.emissive.setHex(0x000000);
            tl.red.material.color.setHex(0x330000);
        } else {
            tl.green.material.emissive.setHex(0x000000);
            tl.green.material.color.setHex(0x003300);
            tl.red.material.emissive.setHex(0xff0000);
            tl.red.material.color.setHex(0xff0000);
        }
    });
}

function updateCars(delta) {
    const stopLine = 5;

    cars.forEach((car, index) => {
        let shouldStop = false;

        // 1. Check Traffic Light (Existing Logic)
        if (car.userData.lane !== laneGreen) {
            let dist = 999;
            let approaching = false;

            if (car.userData.lane === 0 && car.position.z < -stopLine) { dist = Math.abs(car.position.z - (-stopLine)); approaching = true; }
            if (car.userData.lane === 1 && car.position.x > stopLine) { dist = Math.abs(car.position.x - stopLine); approaching = true; }
            if (car.userData.lane === 2 && car.position.z > stopLine) { dist = Math.abs(car.position.z - stopLine); approaching = true; }
            if (car.userData.lane === 3 && car.position.x < -stopLine) { dist = Math.abs(car.position.x - (-stopLine)); approaching = true; }

            if (approaching && dist < 3) {
                shouldStop = true;
                car.userData.waiting = true;
            }
        }

        // 2. Check Collision with Car Ahead
        if (!shouldStop) {
            // Find cars in same lane that are "ahead" and close
            const tooClose = cars.some(other => {
                if (other === car) return false;
                if (other.userData.lane !== car.userData.lane) return false;

                // Calculate vector to other car
                // Because all cars use local TranslateZ, verifying "Front" is complex in World Space without dot product
                // But since lanes are axis algined:
                let dist = 999;
                let isAhead = false;

                if (car.userData.lane === 0) {
                    // Moving +Z. Ahead means other.z > car.z
                    if (other.position.z > car.position.z) {
                        dist = other.position.z - car.position.z;
                        isAhead = true;
                    }
                }
                if (car.userData.lane === 1) {
                    // Moving -X. Ahead means other.x < car.x
                    if (other.position.x < car.position.x) {
                        dist = car.position.x - other.position.x;
                        isAhead = true;
                    }
                }
                if (car.userData.lane === 2) {
                    // Moving -Z. Ahead means other.z < car.z
                    if (other.position.z < car.position.z) {
                        dist = car.position.z - other.position.z;
                        isAhead = true;
                    }
                }
                if (car.userData.lane === 3) {
                    // Moving +X. Ahead means other.x > car.x
                    if (other.position.x > car.position.x) {
                        dist = other.position.x - car.position.x;
                        isAhead = true;
                    }
                }

                return isAhead && dist < 6; // 6 meters safety distance
            });

            if (tooClose) {
                shouldStop = true;
                car.userData.waiting = true;
            }
        }

        if (shouldStop) {
            car.userData.speed = Math.max(0, car.userData.speed - 30 * delta); // Brake
        } else {
            car.userData.speed = Math.min(CAR_SPEED, car.userData.speed + 10 * delta); // Accel
            car.userData.waiting = false;
        }

        car.translateZ(car.userData.speed * delta);

        if (car.position.length() > 60) {
            scene.remove(car);
            cars.splice(index, 1);
        }
    });
}

function toggleCamera() {
    camera.position.set(0, 50, 0);
    camera.lookAt(0, 0, 0);
}

function onWindowResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}

function animate() {
    requestAnimationFrame(animate);
    const delta = 0.016;

    updateLogic();
    updateCars(delta);

    controls.update();
    renderer.render(scene, camera);
}

init();
