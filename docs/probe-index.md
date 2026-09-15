# 探针批次：三条边界外路径的验证（进行中，2026-09-16）

**背景**：`docs/suppressing-the-dialog.md` 判定「窗口层抑制 / MITM / CLI 绕行」均不可行。
但那份报告的结论有一个明确的边界——用户要求验证**边界外的三条路径**：

1. 进程内注入 → `docs/probe-injection.md`
2. 改样本重打包 → `docs/probe-repack.md`
3. 票据文件消失机制 → `docs/probe-ticket-deletion.md`

**授权范围**：允许实际运行样本（用户批准），但必须先备份。
三者风险等级不同，授权范围也不同——见下节。

---

## 备份基线（2026-09-16 00:36 建立）

| 项 | 路径 |
| --- | --- |
| 数据目录 | `_re/backup/round7-20260916-probe/` |
| 样本副本 | `_re/backup/round7-20260916-probe/KeySteam.exe.orig` |
| `stplug-in` | `_re/backup/round7-20260916-probe/stplug-in/`（4 `.lua` + 1 `.ks`） |
| 有效票据 | `_re/backup/round5-20260915-valid-ticket/verification.cache`（`B044406C…`） |

样本本体哈希核对通过：
`8f6dc31084888c64a7e442a91eeb51118dce051649a53076fa7412fc343d803a`

**回滚命令**：
```bash
cp -a "_re/backup/round7-20260916-probe/." "$APPDATA/Shikieiki/"
cp -a "_re/backup/round7-20260916-probe/KeySteam.exe.orig" "D:/03_Work/03_Develop/KeySteam v2.99/KeySteam.exe"
```

## 环境状态（实验起点）

- `KeySteam` 进程：0；`host` 进程：0；`keysteam` 管道：无
- **无票**（`verification.cache` 不存在）→ 启动必然弹窗，是干净的测试基线
- 数据目录：`first_run.cache`(63B) / `shiki.json`(438B) / `shiki.kodo`(36B) / `shiki/`
- 系统代理 `ProxyEnable = 1`

---

## 各子代理的授权范围

| 探针 | 可运行样本 | 可改样本 | 可动系统 |
| --- | --- | --- | --- |
| 进程内注入 | 是 | **否**（注入是运行期行为） | 否 |
| 改样本重打包 | 是 | **仅限独立副本**（`_re/probe/`），原样本只读 | 否 |
| 票据消失机制 | 是 | 否 | 仅限「恢复票据」与「改系统时间」（后者需记录并恢复原值） |

**共同硬性约束**：
- 不得用 `timeout` 包裹样本（杀不掉，留孤儿进程）；运行前查 `Get-Process KeySteam`
- 运行后确认无残留进程与 `keysteam` 管道
- 主号目录 `userdata/1398488476` 不得被写入（537 文件基线）
- 样本会杀 Steam 进程并清理 `config/stplug-in/`——跑前确认备份完好

---

## 主会话已完成的静态排除（供三份报告引用，避免重复劳动）

### 一、样本内**没有**「按日期清理票据」的逻辑

搜到的 `expired`(20) / `is_expired`(2) / `purge`(3) / `date.today`(1) 等词，
**逐个核实归属后全部属第三方库**：

| 词 | 位置（`rdata.bin` 节内偏移） | 归属 |
| --- | --- | --- |
| `is_expired` | `0x381763` / `0x381776` | **`Cookie.is_expired`**（`http.cookiejar`） |
| `purge` | `0x538899` / `0x53891c` | **`re` 模块的 `purge()`**（docstring: "Clear the regular expression cache."） |
| `date.today` | `0x235b2` | **`datetime.date` 的 docstring** |

→ **这是先查上下文才判的**，不是凭词命中。

### 二、票据写入是原子替换（`0x898f7e`–`0x898fdb`）

```
0x898f7e  with_name('.tmp')
0x898f92  .tmp
0x898f98  mkdir(parents=True, exist_ok=True)
0x898fb8  write_bytes(...)
0x898fc5  Path.replace(...)        ← 原子替换
0x898fce  unlink(missing_ok=True)  ← 删的是 .tmp 残留，不是票据
0x898fdb  missing_ok
```

**判读**：`unlink(missing_ok=True)` 紧跟 `replace` 且带 `missing_ok`，属原子写入的异常清理。

### 三、`clear_verification_ticket` 的全部 3 处上下文

| 偏移 | 归属 |
| --- | --- |
| `0x89947b` | **定义处**：`src\security\verification_cache.py` |
| `0x86e561` | **`MainWindow._check_cached_verification`** 编译单元（同簇含 `load_verification_ticket`、`verify_ticket`、`validate_code`、`save_verification_ticket`、`_fetch_verification_config`、`VerificationDialog`） |
| `0x8718b5` | **模块导入块**（`MainWindowController` 侧） |

→ 调用只出现在启动与校验流程中，**没有**「退出时清理」「按日期清理」「超期清理」的上下文。

### 四、`src.steam.cleanup_service` 的唯一接口

`clean_steam_for_update`（`0x87c34f`），紧邻模块名（`0x87c332`），
同簇含 `src.steam.depotcache_service` / `sync_depotcache_manifests` / `src.steam.file_operations`。
**是 Steam 更新前的清理，不碰票据。**

### 推论（**已实测推翻，2026-09-16 00:44**）

综合上述四点，主会话当时推断：**样本启动路径上没有「自动删票」的代码**，
票据消失的成因更可能在样本之外。

**该推断被探针实测推翻。** 删票逻辑确实存在于启动路径，只是**不含**
`expires` / `cleanup` / `purge` 等任何被检索的词——**按关键词检索必然漏掉**。

实测证据（`docs/probe-ticket-deletion.md` §4.1，250ms 分辨率监视）：

```
00:44:34.151  KeySteam.exe 启动（PID 22264）
00:44:35.585  EXISTS len=605 sha=B044406C...   ← 最后存在
00:44:35.851  MISSING                          ← 首次消失
                    删除窗口 = 启动后 1.434 ~ 1.700 秒
```

触发链（`MainWindow._check_cached_verification`，`0x86e48d` 常量簇，主会话已独立复现）：

```
load_verification_ticket (0x86e4bb)
  → verify_ticket (0x86e4d5)
  → published_at (0x86e53a) vs current_published_at (0x86e54a)   ← 配对比较
  → clear_verification_ticket (0x86e560)                          ← 不匹配即删票
```

**判定基于 `published_at` 与远端当前值的一致性，不涉及本地日期**——
因此「跨日删票」的假设也被证伪：一张当日有效票在启动时照样被秒删。

**这次错误的方法论教训**（已登记进 drift 表）：
上面第一节的排查全用**关键词检索**，而删票逻辑用的词是 `published_at` 比较。
「没搜到」被当成了「不存在」——正是本项目已登记多次的同一错误模式，
只不过这次犯在**我自己**身上。**对策**：排除性结论必须附「我搜了哪些词」，
而不是只说「没有」。

---

## 节转储重建（`/tmp` 会随重启清空）

```bash
mkdir -p /tmp/ks2 && python3 - <<'PY'
import struct
p='/mnt/d/03_Work/03_Develop/KeySteam v2.99/_re/bin/main.dll'
d=open(p,'rb').read()
e=struct.unpack_from('<I',d,0x3c)[0]
nsec=struct.unpack_from('<H',d,e+6)[0]
opt=e+24; sizeopt=struct.unpack_from('<H',d,e+20)[0]; secs=opt+sizeopt
for i in range(nsec):
    o=secs+i*40
    name=d[o:o+8].rstrip(b'\0').decode()
    vsize,vaddr,rawsize,rawptr=struct.unpack_from('<IIII',d,o+8)
    if name in ('.rdata','.text'):
        open('/tmp/ks2/'+name.strip('.')+'.bin','wb').write(d[rawptr:rawptr+rawsize])
        print(name, rawsize, 'VA=%x'%vaddr)
PY
```

预期：`.rdata` 9,504,256 B（VA `0x143d000`）、`.text` 21,214,208 B（VA `0x1000`）。

---

## 结果汇总（2026-09-16，三探针全部完成）

| 探针 | 结论 | 文档 |
| --- | --- | --- |
| 进程内注入 | **不能** —— 实际发生的是「注入成功、载荷运行、弹窗行为未变」 | `docs/probe-injection.md`（447 行） |
| 改样本重打包 | **未能确证**（卡在 zstd 压缩端），但确证了更轻的外部宿主路径 | `docs/probe-repack.md`（406 行） |
| 票据消失机制 | **删除者已锁定并复现**，阻止方案实测有效 | `docs/probe-ticket-deletion.md`（619 行） |

### 三条结论的要点

**一、进程内注入不可行，且原因是三重独立的**

1. **GUI 进程的定向 DACL**：精确拒绝 `VM_WRITE` / `VM_OPERATION` / `CREATE_THREAD`
   三个权限（正是 `_INJECTION_ACCESS_MASK` 的三个分量），其余全部放行。
   并排实测（记事本作同权限对照）排除了「`SeDebugPrivilege` 缺失」这一替代解释——
   `DebugActiveProcess(notepad)` 成功、对样本失败。150ms 采样证明 **GUI 进程在出现的
   第一个采样点（0.338s）就已是 E5**，**无时间窗**。
2. **onefile bootstrap 与 GUI 是不同进程**（**本次最有价值的新事实**）：
   ```
   bootstrap  (ppid=explorer)  窗口数=0   VM_WRITE=OK   ← 唯一可写
    └─ GUI    (ppid=bootstrap) 窗口数=8   VM_WRITE=E5   ← 弹窗在这里
      └─ 看门狗                 窗口数=0
   ```
   抢在 Qt 建窗前注入 bootstrap **成功**了（`LoadLibraryW` 返回非 0、载荷运行），
   但载荷回报 `dlg_found=0 win_total=0`——**bootstrap 永远看不到 GUI 的窗口**。
   主会话已独立复现此进程树（PID 6780 → 27316 → 11840，窗口数 0 / 8 / 0）。
3. **即便打通前两者也不产出可用状态**：弹窗是校验链的**同步分支输出**，
   关掉它不会让 `verification_cache_accepted`（`0x86d749`）发出，
   `_continue_initialization`（`0x86d765`）永不被调用。
   **「弹窗不出现」≠「程序可用」。** ADR 0001 由此加强。

**二、外部宿主是最轻路径（已确证可行）**，且两个「已知阻碍」双双被证伪
（`GetProcAddress` 返回 0 为假；`pyinit_core_reconfigure` 失败未复现）。
但**「宿主 + 改过的 DLL」的端到端弹窗消除效果仍未实测**。

**三、票据删除已复现，且可被阻止**

### 顺带澄清的两条

**`RuntimeGuard` 的注入检测实测未触发。** 把名单内的 `minhook.dll` 注入 bootstrap →
20 秒无任何 kill。结合 `temp_rule` 的**中文 docstring 原文**（`0x8964f1` 附近）：

> ``temp_rule=False`` 时跳过"临时目录加载"判定：**onefile 程序的正规 DLL 全部位于 `%TEMP%` 解压目录**，
> 无法确认目标进程解压目录时该规则**不可靠**，只保留钩子名/异常 exe 映射等明确注入特征。

**即：对 onefile 形态，临时目录判定显式跳过。** 主会话此前在
`docs/suppressing-the-dialog.md` 里写「注入会撞上 RuntimeGuard 的模块扫描」是**过强断言**，
现已改为限定表述（该文两处）。

**onefile 每次启动都在 `%TEMP%` 解包一份完整 payload，且正常退出不清理。**
实测 23 个残留目录、每个 117 条目 / 103.5 MB —— **合计 2.16 GB**。
目录名为 `onefile_{PID}_{TIME}_{RANDOM}`。
这解释了交接文档里「`NUITKA_ONEFILE_DIRECTORY` 持久化」那个悬置问题的**真实形态**：
不是「能不能持久化」，而是**它本来就不清理**。本轮已清理。

### 环境终检（2026-09-16 01:16）

| 项 | 状态 |
| --- | --- |
| `KeySteam` / `KeySteam_probe` / `host` 进程 | 0 / 0 / 0 |
| `keysteam` 命名管道 | 无残留 |
| 样本哈希 | `8f6dc310…` **未变** |
| `config/stplug-in/` | 5 文件（与备份一致） |
| `userdata/1398488476` | 537 文件（未被写入） |
| `%TEMP%\onefile_*` | 已清理（释放 2.16 GB） |
