/**
 * Deploy CrowdWiseRegistry and write the address where the backend expects it.
 *
 * After running this against a local Hardhat node, set in .env:
 *   BLOCKCHAIN_PROVIDER=web3
 *   CONTRACT_ADDRESS=<printed address>
 *   BLOCKCHAIN_PRIVATE_KEY=<the recorder key>
 */
import { ethers, network } from "hardhat";
import * as fs from "fs";
import * as path from "path";

async function main() {
  const [deployer] = await ethers.getSigners();
  // The recorder is the backend's signing account. Default it to the deployer
  // for local development; in production it is a dedicated key.
  const recorder = process.env.BLOCKCHAIN_RECORDER_ADDRESS || deployer.address;

  console.log("CrowdWise — deploying CrowdWiseRegistry");
  console.log("  network :", network.name);
  console.log("  deployer:", deployer.address);
  console.log("  recorder:", recorder);

  const factory = await ethers.getContractFactory("CrowdWiseRegistry");
  const registry = await factory.deploy(recorder);
  await registry.waitForDeployment();

  const address = await registry.getAddress();
  const deployTx = registry.deploymentTransaction();
  const receipt = deployTx ? await deployTx.wait() : null;

  console.log("\nDeployed.");
  console.log("  contract    :", address);
  console.log("  tx hash     :", deployTx?.hash);
  console.log("  block number:", receipt?.blockNumber);

  const record = {
    network: network.name,
    chainId: Number((await ethers.provider.getNetwork()).chainId),
    contractAddress: address,
    recorder,
    deployer: deployer.address,
    transactionHash: deployTx?.hash ?? null,
    blockNumber: receipt?.blockNumber ?? null,
    deployedAt: new Date().toISOString(),
  };

  const outDir = path.resolve(__dirname, "../deployments");
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(
    path.join(outDir, `${network.name}.json`),
    JSON.stringify(record, null, 2),
    "utf-8",
  );

  console.log(`\nDeployment written to blockchain/deployments/${network.name}.json`);
  console.log("\nSet these in your .env to switch the backend onto the real chain:");
  console.log("  BLOCKCHAIN_PROVIDER=web3");
  console.log(`  CONTRACT_ADDRESS=${address}`);
  console.log(`  BLOCKCHAIN_RPC_URL=${network.name === "localhost" ? "http://localhost:8545" : process.env.BLOCKCHAIN_RPC_URL}`);
  console.log("  BLOCKCHAIN_PRIVATE_KEY=<the recorder's private key>");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
