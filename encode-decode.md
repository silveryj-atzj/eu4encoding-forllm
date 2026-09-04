# EU4DLL 本地化编码与解码

`eu4dll_codec.py` 用于转换 EU4DLL 中文补丁使用的自定义转义格式。它不是普通的 Latin-1 映射，也不是 UTF-16LE。

## 命令行

```powershell
python eu4dll_codec.py decode input.txt output.txt
python eu4dll_codec.py encode input.txt output.txt
```

- `decode`：读取 UTF-8 文件，在每一行中查找首个 `"` 和最后一个 `"`，只解码两者之间的内容；引号外的文本和换行保持不变。
- `encode`：读取整个 UTF-8 文件，把所有字符编码为 EU4DLL 字节，再将这些字节映射为 UTF-8 文本。它不会按行或按引号筛选内容。
- 输入文件和输出文件不能依赖编辑器的当前代码页，脚本始终按 UTF-8 读写文件。

## EU4DLL 字节格式

普通 CP1252 字符使用一个字节。不能直接表示的字符使用三个字节：

```text
标记 + 低字节 + 高字节
```

标记为 `0x10`、`0x11`、`0x12` 或 `0x13`。`decode_raw` 的还原规则是：

| 标记 | 代码点还原 |
|------|------------|
| `0x10` | 不调整 |
| `0x11` | 减去 `0x0E` |
| `0x12` | 加上 `0x900` |
| `0x13` | 加上 `0x8F2` |

`0x80`-`0x9F` 中的 CP1252 特殊字节会映射为对应的 Unicode 字符，例如 `0x80 -> U+20AC`、`0x8F` 保持为 `U+008F`。文件外层仍是 UTF-8，因此一个 EU4DLL 字节可能在磁盘上变成多个 UTF-8 字节。

## Python API

```python
from eu4dll_codec import decode_raw, encode_raw

text = "这是一个测试"
encoded = encode_raw(text)       # EU4DLL 原始字节
decoded = decode_raw(encoded)    # Unicode 文本
assert decoded == text
```

### 原始字节接口

- `encode_raw(text: str) -> bytes`：逐字符编码。CP1252 可表示的字符输出一个字节，其他字符输出带标记的三字节序列。
- `decode_raw(raw: bytes) -> str`：逐字节解码。遇到 `0x10`-`0x13` 时必须还有两个后续字节，否则抛出 `ValueError`。
- 解码后超出 `U+FFFF`，或落在实现定义的无效范围 `0x101`-`0x98E` 内的代码点，会替换为省略号 `U+2026`。因此这些输入不一定能无损 round-trip。

### 文件接口

```python
from pathlib import Path
from eu4dll_codec import decode_file, encode_file

decoded = decode_file(Path("input.txt").read_bytes())
Path("decoded.txt").write_bytes(decoded)

encoded = encode_file(Path("input.txt").read_bytes())
Path("encoded.txt").write_bytes(encoded)
```

`decode_file` 的处理步骤如下：

1. 将文件整体按 UTF-8 解码。
2. 只处理含有一对引号的行内片段。
3. 将 payload 中的 Unicode 字符还原为 EU4DLL 单字节值。
4. 调用 `decode_raw`，再把结果写回原来的引号位置。

如果 payload 含有无法还原为单字节 CP1252 值的 Unicode 字符，该行会原样保留。换行只按 `CRLF`、`LF` 或 `CR` 识别，不能用 `splitlines()` 替代，因为控制字符可能是 EU4DLL 数据的一部分。

`encode_file` 的处理步骤如下：

1. 将文件整体按 UTF-8 解码。
2. 调用 `encode_raw` 编码全部文本。
3. 将每个 EU4DLL 字节通过 `byte_to_cp1252` 映射为 Unicode 字符。
4. 将结果按 UTF-8 写出。

由于 `encode_file` 会把整个文件编码，包括引号本身，而 `decode_file` 只处理字面引号之间的 payload，两个文件接口不是严格互为逆操作。不要用 `decode_file(encode_file(data))` 验证文件级 round-trip；验证原始文本时应使用：

```python
assert decode_raw(encode_raw(text)) == text
```

## 诊断与注意事项

- 先确认文件是 UTF-8，再判断其中的 Unicode 控制字符是否代表 EU4DLL 标记。不要把 UTF-8 外层字节（例如 `C2 8F`）直接当成 EU4DLL 原始字节。
- 不要把 EU4DLL 格式当作普通 Latin-1，也不要对它使用通用 Latin-1 解码函数。
- 不要使用 `errors="ignore"` 或 `errors="replace"`，否则会丢失无法解码的数据。
- 不要清理 `0x10`、`0x11`、`0x12`、`0x13`、`0x0C`、`0x1D` 等控制字符；前三者可能是三字节序列的标记，后两者可能是数据字节。
- `decode_raw` 遇到不完整的三字节序列会明确报错，而不是静默截断。
- `encode_raw` 对 `0x100 < code_point < 0xA00` 的字符先加上 `0xE000`，再根据保留字节集合选择标记和偏移。不能只按 UTF-16LE 拼接字符。
- 文件编码转换不自动添加或移除 BOM。需要 BOM 时，应在外部明确处理，并确认目标加载器的要求。

## 最小验证

```powershell
python -c "from eu4dll_codec import decode_raw, encode_raw; s='这是一个测试'; assert decode_raw(encode_raw(s)) == s; print('round-trip ok')"
```

已知的 EU4DLL 原始片段也可以直接验证：

```python
from eu4dll_codec import decode_raw

assert decode_raw(bytes((0x10, 0xD9, 0x8F, 0x10, 0x2F, 0x66)))
```
