这是之前的AI未有双字节补丁前的暴力破解经验，但是用了双字节之后就有了正确的解码法。
因此本旧版仅可作为历史参考，实际使用以新版为主

# Paradox 游戏本地化编码与诊断规则

## 1. 角色与核心目标
处理 Paradox 游戏 Mod 本地化时，应进行字节级编码分析并实现无损双向转换。首先要区分普通文本编码和 EU4DLL 中文补丁使用的自定义转义格式，不能看到乱码就默认是 Latin-1 问题。

---

## 2. 技术架构与约束

### 普通 Latin-1 映射（独立场景）

```

中文字符串（Unicode）
│
│ .encode("utf-8")
▼
UTF-8 字节数组（每个中日韩字符通常占 3 个字节）
│
│ .decode("iso-8859-1") [可选添加 b"\xef\xbb\xbf"]
▼
Latin-1 映射字符串（在普通文本编辑器中通常显示为乱码）
│
│ 反向流程：.encode("iso-8859-1") -> 移除 BOM -> .decode("utf-8")
▼
原始中文字符串（Unicode）

```

只有通过字节检查确认文件使用普通 Latin-1 映射时，才能使用这条流程。它不能解码 EU4DLL 转义序列。

### EU4DLL 转义流程

```text
UTF-8 文件字节 -> Unicode 字符 -> 类 CP1252 单字节值
                 -> EU4DLL 转义字节 -> UCS-2 字符 -> UTF-8 文本
```

EU4DLL 对可以直接表示的 CP1252 字符使用单字节。其他 UCS-2 字符使用 `0x10`、`0x11`、`0x12` 或 `0x13` 作为标记，后面跟随低字节和高字节。标记用于记录为避开保留字节而进行的偏移。这不是 UTF-16LE，也不是简单的 Latin-1 映射。

### 游戏环境说明
- **使用 EU4DLL 的 EU4**：UTF-8 本地化文件中包含 EU4DLL 转义层，应使用上面的 EU4DLL 流程。
- **现代引擎（CK3、HOI4、Stellaris）**：通常要求带 BOM 的 `UTF-8`（`EF BB BF`），但仍应以具体引擎和 Mod 工具链为准。
- **旧式补丁工具 / ParaTranz 原始格式**：可能使用 Latin-1 字节映射，转换前必须确认。
- **经典游戏（EU3、Vic2）**：可能直接使用 `Windows-1252`，应以具体版本为准。

---

## 3. 普通 Latin-1 映射的 Python 实现

处理普通 Latin-1 映射文本时，使用以下无损函数。EU4DLL 数据不能使用这些函数：

```python
def zh_to_mod_raw(text: str, add_bom: bool = False) -> str:
    """将 Unicode 编码为普通 Latin-1 映射字符串。"""
    encoded_bytes = text.encode("utf-8")
    if add_bom:
        encoded_bytes = b"\xef\xbb\xbf" + encoded_bytes
    return encoded_bytes.decode("iso-8859-1")

def mod_raw_to_zh(raw_text: str) -> str:
    """将普通 Latin-1 映射字符串解码回 Unicode。"""
    raw_bytes = raw_text.encode("iso-8859-1")
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        raw_bytes = raw_bytes[3:]
    # 关键：不要使用 errors="ignore" 或 errors="replace"，必须保留所有字节。
    return raw_bytes.decode("utf-8")

```

---

## 4. 执行流程与判断逻辑

1. **先进行诊断**：读取并保留原始字节，检查 BOM、UTF-8 有效性，以及解码后的引号内容是否包含 EU4DLL 标记。
* 文件是有效 UTF-8，并不能证明它使用普通 Latin-1 映射。
* 高位字节比例较高只能作为线索，不能单独作为编码判断依据。
* 如果解码后的内容包含 `0x10`-`0x13`，且符合每组三字节的结构，应优先测试 EU4DLL 流程。
* 如果文件不是有效 UTF-8，应单独测试 GBK 或其他已声明编码，不能静默猜测。


2. **双向验证不变量**：普通 Latin-1 映射必须满足 `mod_raw_to_zh(zh_to_mod_raw(text)) == text`。EU4DLL 必须验证 `decode_raw(encode_raw(text)) == text`。
3. **禁止有损截断**：在对应解码器处理之前，必须保留 `\x10`、`\x0C`、`\x1D`、`\x00` 等控制字符。

---

## 5. 禁止事项

* ❌ 声称进行无损转换时，绝不能使用 `errors="ignore"` 或 `errors="replace"`。
* ❌ 不能对已经解码成 Unicode 的 UTF-8 字符串再次执行普通 Latin-1 解码。
* ❌ 不能把 `C2 8F` 这类 UTF-8 文件字节直接交给 EU4DLL 解码器，必须先还原出单字节 `8F`。
* ❌ 不能删除控制字符，也不能对尚未解码的 EU4DLL 数据使用通用 `splitlines()`。
* ❌ 不能把终端或编辑器的显示效果当作编码判定依据。

---
## 补充：编码诊断深入说明（根据实际验证整理）

### A. 字节级检查流程
存在歧义时，应使用十六进制检查，而不是依赖文本显示：
- **UTF-8 BOM**：文件偏移 0 处为 `EF BB BF`。
- **UTF-8 中日韩字符三字节序列**：首字节通常为 `E4`-`E8`，后两个字节为 `80`-`BF`。
- **UTF-16 LE**：`FF FE`（不属于本流程）。
- **普通 Latin-1 / Windows-1252 映射**：确认映射层后，通常表现为无 BOM 的 `80`-`FF` 单字节；60% 的高位字节比例只能作为启发式线索。
- **EU4DLL 转义文本**：原始层中的标记字节为 `10`-`13`，每个标记后面严格跟随两个数据字节。
- 工具参考：PowerShell 使用 `Format-Hex`，类 Unix 环境使用 `xxd`，以检查准确字节。

### B. 终端显示伪象警告
文本编辑器或终端可能使用错误的代码页显示字节，例如 `cp936` 或 `cp1252`。**这不能证明文件使用了 Latin-1。** 如果文件是有效 UTF-8，应先按 UTF-8 解码文件外层。对于 EU4DLL，还要将类 CP1252 的 Unicode 字符还原为单字节值，再执行转义解码。

### C. GBK / 非 UTF-8 边界
如果十六进制采样显示的是 GBK 模式（首字节 `81`-`FE`，次字节 `40`-`FE` 且范围有效），而不是 UTF-8 三字节序列，则该文件**不属于**普通 Latin-1 或 EU4DLL 流程。应先使用明确的 GBK 到 UTF-8 转换步骤，再重新诊断转换后的 UTF-8 文件。

### D. BOM 使用说明
- `zh_to_mod_raw` 中的 `add_bom=True` 会把 BOM 字节加入普通映射 payload；只有目标加载器明确要求时才使用。
- 对 Paradox 的 `.yml` 文件，应将文件级 BOM 与映射或转义 payload 分开处理。默认不要插入内嵌 BOM。

---

## 实战案例与经验总结 (2026年9月)

### 案例：EU4DLL 本地化文本双向编码转换

#### 修正说明
此前把 EU4DLL 生成的内容误判为普通 Latin-1 映射，并据此记录了未实际生成的文件；该结论已删除。

EU4DLL 补丁的静态字符串和公开源码表明，它会把 UTF-8 文本先转为 UCS-2，再编码为自定义的 EU4 转义字节。它不是 `UTF-8 -> ISO-8859-1` 的简单转换。

#### 关键发现与最佳实践

**1. 文件外层编码与 EU4DLL 字节层必须分开**
```
磁盘文件中的乱码字符（UTF-8）
│  先按 UTF-8 解码为 Unicode 字符
▼
按 CP1252 取回单字节值（例如 U+008F -> 8F，U+0152 -> 8C）
│
▼
EU4DLL 转义解码
```

例如，原始字节 `8F` 写入 UTF-8 文件后会变成 `C2 8F`。`C2` 是 UTF-8 外层字节，不属于 EU4DLL 转义内容；必须先还原为 `8F`。

**2. 控制字符保留**
`0x10`、`0x11`、`0x12`、`0x13` 是三字节转义序列的标记，后面必须保留两个字节。`0x0C`、`0x1D` 等也可能是序列中的数据，不能使用通用 `splitlines()`、清理控制字符或 `errors="ignore"`。

**3. EU4DLL 转义规则**
```text
普通 CP1252 字符：                1 个字节
其他 UCS-2 字符：                 标记 + 低字节 + 高字节
标记 = 0x10、0x11、0x12、0x13
解码 0x11：代码点 -= 0x0E
解码 0x12：代码点 += 0x900
解码 0x13：代码点 += 0x8F2
```

编码时，如果高/低字节属于 EU4 保留字节集合，标记和对应偏移必须按补丁算法处理。不能只把每三个字节直接解释成 UTF-16LE。

**4. 编码诊断流程**
```
文件 → 先按 UTF-8 解码文件外层
                  ↓
引号内容含 0x10-0x13 标记特征？ → 按 EU4DLL 转义流程
                  ↓ 否
检查 BOM、UTF-8、GBK 或普通 Latin-1 映射
```

#### 经验教训

| 问题 | 原因 | 解决方案 |
|------|------|--------|
| 文件显示乱码 | EU4DLL 转义层被当作普通文本 | 先还原 CP1252 单字节，再按 EU4DLL 算法解码 |
| 转换失败 | 误用`errors="ignore"` | 严格按照规范，保留所有字节 |
| 结果出现 `쉦` 或乱码控制符 | 把 UTF-8 的 `C2 8F` 当成原始 `8F` 前的额外字节 | 先执行文件 UTF-8 → Unicode → CP1252 字节还原 |
| 结果被拆成多行 | `0x0C` 等控制字节被通用分行函数识别 | 只按实际 CRLF/LF/CR 分行 |

#### 工具链建议

工作区的 `eu4dll_codec.py` 提供文件级转换：
```powershell
python eu4dll_codec.py decode input.txt output.txt
python eu4dll_codec.py encode input.txt output.txt
```

验证时至少检查：解码后的已知样本、引号内容的 Unicode 代码点、原始转义字节长度，以及 `decode_raw(encode_raw(text)) == text`。不要用 `splitlines()` 处理尚未解码的 EU4DLL 数据。

#### 已验证样本
- `bjzm_har_decisions_title` 的乱码行可还原为 `【百家争鸣，思教和谐】`。
- `CS3` 的 `"\x10\x0ET\x10f\x8F\x10\x08^"` 可还原为 `后车师`。
- 另一个汉化工具生成的 `\x10Ù\x8F\x10/f\x11\x0EN\x10*N\x10Km\x10Õ‹` 可还原为 `这是一个测试`。
- 工作区的 `eu4dll_codec.py` 实现了文件级和原始字节级转换；解码结果应使用已知中文、字节长度和双向转换验证。