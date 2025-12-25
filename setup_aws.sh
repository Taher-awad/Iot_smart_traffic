#!/bin/bash
# AWS IoT Setup for Traffic System
THING_NAME="TrafficGateway_Pi"
POLICY_NAME="Traffic_Policy"

echo "--- CREATING AWS IOT RESOURCES ---"

# 1. Create the Thing
aws iot create-thing --thing-name $THING_NAME

# 2. Create Certificates (Saves them to current folder)
aws iot create-keys-and-certificate \
    --set-as-active \
    --certificate-pem-outfile certificate.pem.crt \
    --public-key-outfile public.pem.key \
    --private-key-outfile private.pem.key > cert_output.json

# Extract Certificate ARN for attachment
CERT_ARN=$(jq -r '.certificateArn' cert_output.json)

# 3. Create a Policy (Allows Connect, Publish, Subscribe)
aws iot create-policy \
    --policy-name $POLICY_NAME \
    --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"iot:*","Resource":"*"}]}'

# 4. Attach Policy to Certificate
aws iot attach-policy \
    --policy-name $POLICY_NAME \
    --target $CERT_ARN

# 5. Attach Certificate to Thing
aws iot attach-thing-principal \
    --thing-name $THING_NAME \
    --principal $CERT_ARN

# 6. Download Root CA (Required for connection)
curl -o root-CA.crt https://www.amazontrust.com/repository/AmazonRootCA1.pem

# 7. Get your AWS Endpoint
ENDPOINT=$(aws iot describe-endpoint --endpoint-type iot:Data-ATS --query endpointAddress --output text)

echo ""
echo "================================================="
echo "SETUP COMPLETE!"
echo "Your AWS Endpoint: $ENDPOINT"
echo "Certificates saved in current folder."
echo "================================================="
