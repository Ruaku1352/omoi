# frontend — Firebase Hosting Deploy Unit

React 19.2 + TypeScript + Vite 8 の Static SPA。Node.js 24 LTS系。
3D Preview は three + @react-three/fiber v9系、2D Edit は konva + react-konva。

未Scaffold。担当（まなみん）が `npm create vite@latest . -- --template react-ts` 等で初期化する。
実装前提は `/AGENTS.md` §6・§7 と `skills/frontend/SKILL.md` を参照。

共通Mock: `../contracts/mock/artwork.json` + `../contracts/assets/`
接続先切り替え: `VITE_API_BASE_URL`
