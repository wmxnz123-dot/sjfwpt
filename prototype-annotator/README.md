# 原型标注说明

本目录由 `prototype-annotator` skill 生成，用于保存原型页面的标注数据和运行时资源。

## 目录说明

- `annotations.json`：标注数据源。AI 生成和页面内手动编辑后的标注最终都应写入这里。
- `page-map.json`：原型扫描结果，用于重新生成标注或校验 selector。
- `history.jsonl`：本地在线评审服务写入的编辑历史。
- `runtime/`：标注层所需的 JavaScript 和 CSS 运行时资源。

## 如何启动在线标注

请从当前原型项目根目录启动随项目提供的评审服务：

```bash
python3 prototype-annotator/server.py
```

默认仅允许本机访问，随后打开：

```bash
http://127.0.0.1:8765/index.html
```

需要让局域网设备访问时，可显式指定监听地址：

```bash
python3 prototype-annotator/server.py --host 0.0.0.0 --port 8765
```

在浏览器中打开该服务地址即可在线查看、编辑、新增、删除和导出标注。页面内保存的修改会通过本地评审服务回写到本目录的 `annotations.json`，并在 `history.jsonl` 记录操作历史。

## 注意事项

- 不要用普通静态服务（例如 `python3 -m http.server`）进行人工编辑，因为它不能处理回写请求；页面修改只能暂存在浏览器 `localStorage` 草稿中。
- 对外部署时，必须部署为可运行 Python 服务的应用/容器，并将请求转发到 `prototype-annotator/server.py`；纯静态托管无法安全地把访客的修改写回项目文件。若希望多人编辑且长期保存，建议把该 API 改接数据库和账号权限，而非让公开访客直接写 JSON 文件。
- 静态 HTML 中内嵌的标注 JSON 只是离线或读取失败时的兜底快照，正式数据源仍是本目录的 `annotations.json`。
- 如果更新了 skill 的运行时修复，需要重新执行注入命令，或刷新本目录 `runtime/` 下的运行时文件。
- 如需清空或删除标注结果，请运行 `python3 /path/to/prototype-annotator/scripts/clear_annotations.py /path/to/your/prototype`。该命令会移除标注数据和静态 HTML 注入块，但不会删除 React/Vue adapter 源码，以免破坏原型构建。
