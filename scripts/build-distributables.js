const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const projectRoot = path.resolve(__dirname, "..");
const packageJson = require(path.join(projectRoot, "package.json"));
const outputDirectory = fs.mkdtempSync(
  path.join(os.tmpdir(), "smart-file-organizer-build-"),
);
const destinationDirectory = path.join(projectRoot, "dist");
const electronBuilder = require.resolve("electron-builder/cli.js", {
  paths: [projectRoot],
});

const build = spawnSync(
  process.execPath,
  [
    electronBuilder,
    "--win",
    `--config.directories.output=${outputDirectory}`,
  ],
  { cwd: projectRoot, stdio: "inherit" },
);

if (build.error) {
  throw build.error;
}

const artifacts = fs
  .readdirSync(outputDirectory, { withFileTypes: true })
  .filter(
    (entry) =>
      entry.isFile() &&
      [".exe", ".zip"].includes(path.extname(entry.name).toLowerCase()),
  );
const expectedInstaller = `${packageJson.build.productName} Setup ${packageJson.version}.exe`;
const portableExecutables = artifacts.filter(
  (artifact) =>
    path.extname(artifact.name).toLowerCase() === ".exe" &&
    artifact.name !== expectedInstaller,
);
const hasZip = artifacts.some(
  (artifact) => path.extname(artifact.name).toLowerCase() === ".zip",
);
const hasInstaller = artifacts.some(
  (artifact) => artifact.name === expectedInstaller,
);

fs.mkdirSync(destinationDirectory, { recursive: true });
for (const artifact of artifacts) {
  const sourcePath = path.join(outputDirectory, artifact.name);
  const destinationPath = path.join(destinationDirectory, artifact.name);
  fs.copyFileSync(sourcePath, destinationPath);
  console.log(`Build artifact saved to ${destinationPath}`);
}

fs.rmSync(outputDirectory, { recursive: true, force: true });

if (build.status !== 0) {
  process.exitCode = build.status ?? 1;
}

if (portableExecutables.length === 0 || !hasZip || !hasInstaller) {
  throw new Error(
    `Expected portable executable, ZIP archive, and NSIS installer. Produced ${portableExecutables.length} portable executable(s), ZIP: ${hasZip}, installer: ${hasInstaller}.`,
  );
}
