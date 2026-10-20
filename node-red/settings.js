// Sentinel-AI — configuração do Node-RED (camada low-code de controlo e monitorização).
// Só escuta em 127.0.0.1. As credenciais vêm do .env (variáveis de ambiente), nunca dos fluxos.
module.exports = {
    uiHost: "127.0.0.1",
    uiPort: parseInt(process.env.NODE_RED_PORT || "1880", 10),
    flowFile: "flows.json",
    flowFilePretty: true,
    credentialSecret: false,
    functionExternalModules: false,
    exportGlobalContextKeys: false,
    logging: { console: { level: "info", metrics: false, audit: false } },
    editorTheme: {
        projects: { enabled: false },
        page: { title: "Sentinel-AI · Node-RED" },
        header: { title: "Sentinel-AI (EDCA) — fluxos de controlo" },
        tours: false
    },
    functionGlobalContext: {}
};
