import { spawn } from 'node:child_process';

const npxCommand = process.platform === 'win32' ? 'npx.cmd' : 'npx';
const server = spawn(
  npxCommand,
  ['-y', 'agentation-mcp', 'server'],
  {
    stdio: ['pipe', 'inherit', 'inherit'],
  },
);

const stopServer = (signal) => {
  if (!server.killed) {
    server.kill(signal);
  }
};

process.on('SIGINT', () => stopServer('SIGINT'));
process.on('SIGTERM', () => stopServer('SIGTERM'));

server.on('error', (error) => {
  console.error('Failed to start Agentation MCP:', error);
  process.exitCode = 1;
});

server.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }

  process.exitCode = code ?? 0;
});
