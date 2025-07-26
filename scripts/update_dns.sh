#!/bin/bash

# DNS Update Script for Hokm Game Failover
# Customize this script based on your DNS provider

set -e

NEW_SERVER="$1"
DOMAIN="hokm-game.yourdomain.com"  # Replace with your actual domain

if [ -z "$NEW_SERVER" ]; then
    echo "Usage: $0 <new_server_ip>"
    exit 1
fi

echo "Updating DNS for $DOMAIN to point to $NEW_SERVER"

# Method 1: Cloudflare API (uncomment and configure)
# CLOUDFLARE_API_TOKEN="your_api_token_here"
# ZONE_ID="your_zone_id_here"
# RECORD_ID="your_record_id_here"
# 
# curl -X PUT "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records/$RECORD_ID" \
#      -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
#      -H "Content-Type: application/json" \
#      --data "{\"type\":\"A\",\"name\":\"hokm-game\",\"content\":\"$NEW_SERVER\",\"ttl\":300}"

# Method 2: AWS Route53 (uncomment and configure)
# HOSTED_ZONE_ID="your_hosted_zone_id"
# 
# aws route53 change-resource-record-sets --hosted-zone-id "$HOSTED_ZONE_ID" \
#     --change-batch "{
#         \"Changes\": [{
#             \"Action\": \"UPSERT\",
#             \"ResourceRecordSet\": {
#                 \"Name\": \"$DOMAIN\",
#                 \"Type\": \"A\",
#                 \"TTL\": 300,
#                 \"ResourceRecords\": [{\"Value\": \"$NEW_SERVER\"}]
#             }
#         }]
#     }"

# Method 3: DigitalOcean API (uncomment and configure)
# DO_API_TOKEN="your_do_api_token"
# DOMAIN_NAME="yourdomain.com"
# RECORD_NAME="hokm-game"
# 
# # Get record ID first
# RECORD_ID=$(curl -X GET \
#   -H "Content-Type: application/json" \
#   -H "Authorization: Bearer $DO_API_TOKEN" \
#   "https://api.digitalocean.com/v2/domains/$DOMAIN_NAME/records" | \
#   jq -r ".domain_records[] | select(.name==\"$RECORD_NAME\") | .id")
# 
# # Update the record
# curl -X PUT \
#   -H "Content-Type: application/json" \
#   -H "Authorization: Bearer $DO_API_TOKEN" \
#   -d "{\"data\":\"$NEW_SERVER\",\"ttl\":300}" \
#   "https://api.digitalocean.com/v2/domains/$DOMAIN_NAME/records/$RECORD_ID"

# Method 4: Generic nsupdate (for BIND DNS servers with dynamic updates)
# nsupdate << EOF
# server your-dns-server.com
# zone yourdomain.com
# update delete $DOMAIN A
# update add $DOMAIN 300 A $NEW_SERVER
# send
# EOF

# Method 5: Local hosts file update (for testing)
echo "Updating local hosts file for testing..."
sudo sed -i "/$DOMAIN/d" /etc/hosts
echo "$NEW_SERVER $DOMAIN" | sudo tee -a /etc/hosts

echo "DNS update completed: $DOMAIN -> $NEW_SERVER"
