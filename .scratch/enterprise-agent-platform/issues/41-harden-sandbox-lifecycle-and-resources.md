# 41: 沙盒生命週期與資源限制強化（審查後續：09）

**What to build:** CLI 沙盒在任何結束路徑都會清乾淨：任務被取消（例如用戶端斷線）時容器會被 kill，逾時被取消的 `docker run` 用戶端會被回收而不留殭屍程序。記憶體上限包含 swap，掛入的 `/workspace` 在 rootful 與非 root 映像下都可讀。`target_file` 等路徑參數在準備階段就檢查 `..` 與敏感路徑，被擋下時寫入稽核，不會先讀瀏覽器檔案才丟出普通錯誤。

**Blocked by:** 39: CLI 準備流程與執行結果型別整併

**Status:** ready-for-agent

- [ ] 取消與逾時路徑都 kill 容器並等待 `docker` 用戶端程序結束；Semaphore 在容器確實結束後才釋放
- [ ] 加上 `--memory-swap` 與 `--memory` 同值；容器以明確的 `--user` 執行且工作區權限可讀
- [ ] 路徑型參數在準備階段驗證（含 `..`、敏感路徑），違規寫入 `security_audit_logs` 且不觸發瀏覽器讀取
- [ ] 測試以假程序覆蓋取消、逾時、路徑攔截三種情境
