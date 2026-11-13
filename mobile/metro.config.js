// Learn more: https://docs.expo.dev/guides/customizing-metro/
const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);

// ECharts/zrender (Phase 6.6) import `tslib`; through its package exports Metro picks
// `tslib/modules/index.js`, whose default import of the CommonJS build is undefined on Hermes
// ("Cannot read property '__extends' of undefined"). The ES module build has the same helpers.
const resolveRequest = config.resolver.resolveRequest;
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (moduleName === "tslib") {
    return context.resolveRequest(context, "tslib/tslib.es6.js", platform);
  }
  return resolveRequest
    ? resolveRequest(context, moduleName, platform)
    : context.resolveRequest(context, moduleName, platform);
};

module.exports = config;
