# 46: 前端錯誤訊息擷取共用化（審查後續：10）

**What to build:** 前端所有 `catch` 都用 `caught instanceof Error ? caught.message : "預設訊息"` 取錯誤文字，目前散在 25 處以上（`chat`、`studio`、`connectors`、`org-chart`、`ArtifactViewer`、`AgentWizard`、`SkillEditorModal`、`HeartbeatSection`、`DaemonPairingSection`、`wsClientToolRunner` 等）。改成一個共用函式，例如 `errorMessage(caught, "預設訊息")`，畫面上顯示的繁中錯誤文字不變。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `src/lib/` 新增共用函式，所有現有呼叫點改用它
- [ ] 各畫面的預設錯誤文字維持原樣
- [ ] `tsc` 與前端建置通過
- [ ] 瀏覽器抽查兩個畫面的錯誤提示仍正常顯示
