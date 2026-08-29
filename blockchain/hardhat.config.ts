import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";
import * as dotenv from "dotenv";
import * as path from "path";

// Blockchain config comes from the same .env as the rest of the stack, so the
// backend and the chain tooling can never disagree about which network or
// contract they are talking to.
dotenv.config({ path: path.resolve(__dirname, "../.env") });
dotenv.config();

const RPC_URL = process.env.BLOCKCHAIN_RPC_URL || "http://127.0.0.1:8545";
const PRIVATE_KEY = process.env.BLOCKCHAIN_PRIVATE_KEY || "";
const CHAIN_ID = Number(process.env.BLOCKCHAIN_CHAIN_ID || 31337);

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: { enabled: true, runs: 200 },
      // The registry is small on purpose; keeping it audit-friendly matters
      // more than shaving the last few gas units.
      viaIR: false,
    },
  },
  networks: {
    hardhat: {
      chainId: 31337,
    },
    localhost: {
      url: "http://127.0.0.1:8545",
      chainId: 31337,
    },
    // Any EVM testnet: point BLOCKCHAIN_RPC_URL at it and supply a key.
    testnet: {
      url: RPC_URL,
      chainId: CHAIN_ID,
      accounts: PRIVATE_KEY ? [PRIVATE_KEY] : [],
    },
  },
  paths: {
    sources: "./contracts",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts",
  },
  mocha: {
    timeout: 60000,
  },
};

export default config;
