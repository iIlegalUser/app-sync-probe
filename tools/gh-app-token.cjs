#!/usr/bin/env node
/**
 * 用 GitHub App 的 (App ID + 安装 ID + 私钥) 换一个 installation access token，
 * 打印到 stdout（只打印 token 本身，方便 `$(...)` 嵌套进 git push 的 URL）。
 *
 * 用法:
 *   node gh-app-token.cjs
 * 环境变量（或同名 CLI 参数 --app-id 等）:
 *   APP_ID              GitHub App 的 App ID
 *   APP_INSTALLATION_ID App 安装到本仓库后得到的 Installation ID
 *   APP_PRIVATE_KEY     PEM 私钥全文（可用 \n 字面量转义）
 *
 * 设计要点:
 *   - 只申请 Contents / Workflows 两个写权限（downscope），App 自身权限再大也没用。
 *   - 不落盘、不打印 PEM、出错只报 HTTP 状态与 message，避免私钥/token 进日志。
 */
const crypto = require("node:crypto");

function arg(name, envName) {
  const i = process.argv.indexOf(`--${name}`);
  if (i !== -1 && process.argv[i + 1]) return process.argv[i + 1];
  return process.env[envName] || "";
}

function b64url(buf) {
  return Buffer.from(buf).toString("base64url");
}

function makeJwt(appId, privateKey) {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  // iat 往前放 60 秒抵消本机与 GitHub 的时钟偏差；GitHub 要求 exp - iat <= 600
  const payload = { iat: now - 60, exp: now + 540, iss: appId };
  const signingInput = `${b64url(JSON.stringify(header))}.${b64url(JSON.stringify(payload))}`;
  const sig = crypto.sign("RSA-SHA256", Buffer.from(signingInput), privateKey);
  return `${signingInput}.${b64url(sig)}`;
}

async function main() {
  const appId = arg("app-id", "APP_ID").trim();
  const installationId = arg("installation-id", "APP_INSTALLATION_ID").trim();
  let key = arg("private-key", "APP_PRIVATE_KEY").trim();
  if (!appId || !installationId || !key) {
    throw new Error("缺少参数: 需要 APP_ID / APP_INSTALLATION_ID / APP_PRIVATE_KEY");
  }
  // secret 里存 PEM 时换行常被转义成字面量 \n；真实多行 PEM 里不会有反斜杠
  if (key.includes("\\n")) key = key.replace(/\\n/g, "\n");
  // GitHub 生成的 .pem 是 PKCS#1("BEGIN RSA PRIVATE KEY")，Node 两种都能吃

  const jwt = makeJwt(appId, key);
  const res = await fetch(
    `https://api.github.com/app/installations/${installationId}/access_tokens`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      // downscope: 只给推送本次提交需要的两个权限
      body: JSON.stringify({ permissions: { contents: "write", workflows: "write" } }),
    },
  );

  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(`换取 installation token 失败: HTTP ${res.status} ${body.message || ""}`.trim());
  }
  if (!body.token) {
    throw new Error("响应里没有 token 字段");
  }
  return body.token;
}

// 注意：不要在 fetch 之后用 process.exit()。Windows 上 Node 24 会在退出时断言失败
// （uv async handle closing），stdout/stderr 可能丢失。改为设置 exitCode 让它自然结束。
main()
  .then((token) => {
    process.stdout.write(token);
  })
  .catch((err) => {
    console.error(`未预期错误: ${err.message}`);
    process.exitCode = 1;
  });
