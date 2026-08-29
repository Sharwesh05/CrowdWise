# Local Hardhat node + CrowdWiseRegistry deployment
FROM node:20-bullseye-slim

WORKDIR /app

COPY blockchain/package.json blockchain/package-lock.json* ./
RUN npm install

COPY blockchain/ ./
RUN npx hardhat compile

EXPOSE 8545

# Start the node, wait for it to accept connections, then deploy the registry so
# the contract address is available as soon as the container is healthy.
COPY infrastructure/docker/hardhat-entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD node -e "fetch('http://localhost:8545',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',method:'eth_blockNumber',params:[],id:1})}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
