# examples/ —— 可删除的示例

此目录存放与模板核心无关的参考内容，方便你了解产出物是怎么做出来的；不需要就整目录删掉，不影响运行与测试。

## `docx/` —— 把 Markdown 文档转成 Word

早期用于把文档集批量导出为 Word。它依赖 `python-docx`（不在 `requirements.txt` 里），且渲染配置（A4、中文字体、页眉页脚、目录）是按中文技术文档调的。

自己用时：

```bash
pip install python-docx
python examples/docx/md_to_docx.py     # 渲染 docs/ 下的 Markdown 为同名 .docx
python examples/docx/verify_docx.py    # 检查生成的文档结构
```

脚本默认读取项目根目录下的 `docs/`，被渲染文件的路径与页眉规则需要按你的目录结构微调。

> 如果你的项目不需要 Word 产出物，直接删除本目录即可。
