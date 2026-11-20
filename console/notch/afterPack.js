'use strict';

// 打包收尾：①把控制台后端整套本地模块按仓库原布局快照进 Resources/console-backend/
// （app.py 在 console/ 子目录下，自身会把 parents[1] 插进 sys.path，所以根目录模块平铺在
//  console-backend/ 即可复刻解析关系）；②arm64 上未签名二进制无法运行，统一打 ad-hoc 签名并校验。
// 注意：改了 console/app.py 或任何被它依赖的本地模块后，需要重新打包 App 才会带上新代码。
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.join(__dirname, '..', '..');

exports.default = async function afterPack(context) {
  const appPath = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  const resources = path.join(appPath, 'Contents', 'Resources');
  const backendDir = path.join(resources, 'console-backend');

  fs.rmSync(backendDir, { recursive: true, force: true });
  fs.mkdirSync(path.join(backendDir, 'console'), { recursive: true });
  for (const entry of fs.readdirSync(path.join(__dirname, '..'))) {
    if (entry.endsWith('.py') || entry === 'wallet_catalog.json') {
      fs.copyFileSync(path.join(__dirname, '..', entry), path.join(backendDir, 'console', entry));
    }
  }
  for (const entry of fs.readdirSync(REPO_ROOT)) {
    if (entry.endsWith('.py')) {
      fs.copyFileSync(path.join(REPO_ROOT, entry), path.join(backendDir, entry));
    }
  }

  execSync(`codesign --force --deep --sign - "${appPath}"`, { stdio: 'inherit' });
  execSync(`codesign --verify --deep --strict "${appPath}"`, { stdio: 'inherit' });
};
