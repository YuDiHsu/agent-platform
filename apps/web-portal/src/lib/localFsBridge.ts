// Implements: REQ-004, REQ-012 (Chromium File System Access API + IndexedDB + path denylist)
import { get as idbGet, set as idbSet } from "idb-keyval";

const FORBIDDEN_PATTERNS = [
  /(^|\/)\.env($|\.)/i,
  /\.pem$/i,
  /\.pfx$/i,
  /(^|\/)id_rsa($|\.)/i,
  /(^|\/)\.git(\/|$)/i,
  /(^|\/)node_modules(\/|$)/i,
];

export const UNSUPPORTED_DIRECTORY_GUIDANCE =
  "這個瀏覽器不能授權本機資料夾。請改用桌面版 Chrome 或 Microsoft Edge。手機上的 Chrome、Edge 與 Safari 都不支援直接讀寫本機資料夾。";

export interface LocalFileEntry {
  path: string;
  size: number;
  lastModified: number;
}

export type HandleRestore = "connected" | "needs-permission" | "missing";

export function directoryPickerSupported(): boolean {
  return typeof window !== "undefined" && "showDirectoryPicker" in window;
}

export function isForbiddenLocalPath(relativePath: string): boolean {
  const normalized = relativePath.replace(/\\/g, "/");
  if (normalized.split("/").some((segment) => segment === "..")) return true;
  return FORBIDDEN_PATTERNS.some((pattern) => pattern.test(normalized));
}

export class BrowserLocalFsBridge {
  static async authorizeAndMountDirectory(): Promise<{
    handleKey: string;
    folderName: string;
    fileTree: LocalFileEntry[];
  }> {
    if (!directoryPickerSupported()) {
      throw new Error(UNSUPPORTED_DIRECTORY_GUIDANCE);
    }
    const dirHandle = await window.showDirectoryPicker({ mode: "readwrite" });
    const handleKey = `local_mount_${crypto.randomUUID()}`;
    await idbSet(handleKey, dirHandle);
    const fileTree = await this.scanDirectoryTree(dirHandle, "");
    return { handleKey, folderName: dirHandle.name, fileTree };
  }

  static async inspectHandle(handleKey: string): Promise<HandleRestore> {
    const dirHandle = await idbGet<FileSystemDirectoryHandle>(handleKey);
    if (!dirHandle) return "missing";
    const state = await dirHandle.queryPermission({ mode: "readwrite" });
    return state === "granted" ? "connected" : "needs-permission";
  }

  static async ensurePermission(
    handleKey: string,
    mode: "read" | "readwrite" = "read",
  ): Promise<FileSystemDirectoryHandle> {
    const dirHandle = await idbGet<FileSystemDirectoryHandle>(handleKey);
    if (!dirHandle) throw new Error("找不到本機資料夾授權紀錄，請重新綁定。");
    const options = { mode };
    if ((await dirHandle.queryPermission(options)) === "granted") return dirHandle;
    if ((await dirHandle.requestPermission(options)) === "granted") return dirHandle;
    throw new Error("使用者拒絕授予本機資料夾存取權限。");
  }

  static async scanDirectoryTree(
    dirHandle: FileSystemDirectoryHandle,
    prefix: string,
    maxFiles = 500,
  ): Promise<LocalFileEntry[]> {
    const results: LocalFileEntry[] = [];
    for await (const [name, handle] of dirHandle.entries()) {
      const relPath = prefix ? `${prefix}/${name}` : name;
      if (isForbiddenLocalPath(relPath) || isForbiddenLocalPath(name)) continue;
      if (handle.kind === "file") {
        const file = await handle.getFile();
        results.push({ path: relPath, size: file.size, lastModified: file.lastModified });
        if (results.length >= maxFiles) break;
      } else {
        const sub = await this.scanDirectoryTree(handle, relPath, maxFiles - results.length);
        results.push(...sub);
      }
    }
    return results;
  }

  static async readFileForAgent(
    handleKey: string,
    relativePath: string,
  ): Promise<{ encoding: "utf-8" | "base64"; mimeType: string; content: string; size: number }> {
    if (isForbiddenLocalPath(relativePath)) {
      throw new Error(`Security Violation: 禁止讀取敏感或越權路徑 (${relativePath})`);
    }
    const rootHandle = await this.ensurePermission(handleKey, "read");
    const fileHandle = await this.resolveFileHandle(rootHandle, relativePath, false);
    const file = await fileHandle.getFile();
    if (/\.(docx|xlsx|pdf|pptx)$/i.test(relativePath)) {
      const buffer = await file.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      let binary = "";
      const step = 0x8000;
      for (let index = 0; index < bytes.length; index += step) {
        binary += String.fromCharCode(...bytes.subarray(index, index + step));
      }
      return {
        encoding: "base64",
        mimeType: file.type || "application/octet-stream",
        content: btoa(binary),
        size: file.size,
      };
    }
    return { encoding: "utf-8", mimeType: "text/plain", content: await file.text(), size: file.size };
  }

  static async commitConfirmedWrite(handleKey: string, relativePath: string, newContent: string): Promise<void> {
    if (isForbiddenLocalPath(relativePath)) {
      throw new Error(`Security Violation: 禁止寫入敏感路徑 (${relativePath})`);
    }
    const rootHandle = await this.ensurePermission(handleKey, "readwrite");
    const fileHandle = await this.resolveFileHandle(rootHandle, relativePath, true);
    const writable = await fileHandle.createWritable();
    await writable.write(newContent);
    await writable.close();
  }

  private static async resolveFileHandle(
    root: FileSystemDirectoryHandle,
    relPath: string,
    create: boolean,
  ): Promise<FileSystemFileHandle> {
    const parts = relPath.split("/").filter(Boolean);
    let currentDir = root;
    for (let index = 0; index < parts.length - 1; index += 1) {
      currentDir = await currentDir.getDirectoryHandle(parts[index], { create });
    }
    return currentDir.getFileHandle(parts[parts.length - 1], { create });
  }
}
