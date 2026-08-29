#!/usr/bin/env bash
# Start a local Hardhat node and deploy CrowdWiseRegistry onto it.
#
# The deployment record is written to blockchain/deployments/localhost.json,
# which is a mounted volume, so the host can read the contract address and set
# CONTRACT_ADDRESS for the backend.
set -euo pipefail

echo "[crowdwise-chain] starting hardhat node on 0.0.0.0:8545"
npx hardhat node --hostname 0.0.0.0 --port 8545 &
NODE_PID=$!

# Wait for the RPC endpoint to answer rather than sleeping a fixed interval.
echo "[crowdwise-chain] waiting for RPC…"
for attempt in $(seq 1 60); do
  if node -e "fetch('http://localhost:8545',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',method:'eth_blockNumber',params:[],id:1})}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" 2>/dev/null; then
    echo "[crowdwise-chain] RPC is up after ${attempt}s"
    break
  fi
  sleep 1
done

echo "[crowdwise-chain] deploying CrowdWiseRegistry…"
if npx hardhat run scripts/deploy.ts --network localhost; then
  echo "[crowdwise-chain] deployment complete"
else
  echo "[crowdwise-chain] deployment FAILED — the node stays up so you can retry manually" >&2
fi

# Keep the node in the foreground so the container lives as long as it does.
wait "$NODE_PID"
