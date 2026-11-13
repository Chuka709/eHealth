// Learn more: https://docs.expo.dev/guides/customizing-metro/
const path = require("node:path");
const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);

// ECharts/zrender (Phase 6.6) import `tslib`; through its package exports Metro picks
// `tslib/modules/index.js`, whose default import of the CommonJS build is undefined on Hermes
// ("Cannot read property '__extends' of undefined"). The ES module build has the same helpers;
// it is named by its file (not a subpath the package does not export).
const tslibEs6 = path.join(path.dirname(require.resolve("tslib")), "tslib.es6.js");
const resolveRequest = config.resolver.resolveRequest;
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (moduleName === "tslib") {
    return { type: "sourceFile", filePath: tslibEs6 };
  }
  return resolveRequest
    ? resolveRequest(context, moduleName, platform)
    : context.resolveRequest(context, moduleName, platform);
};

module.exports = config;
