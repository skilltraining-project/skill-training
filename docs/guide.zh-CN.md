# 使用指南

[项目介绍](../README.zh-CN.md) · [English](guide.md) · 简体中文

先按[快速开始](../README.zh-CN.md#快速开始)准备环境、跑通示例。这里介绍如何使用自己的材料、单独运行各个阶段、检查训练记录，以及设计对照实验。

## 准备自己的材料

使用你有权处理的材料，每部作品放在独立目录中：

```text
data/my-work/
├── human/
│   ├── ep01.txt
│   ├── ep02.txt
│   └── ...
└── story.md
```

`human/` 中保存作为参考的人类剧本；`story.md` 是 `s1_diffuse.py` 生成的、去掉创作细节后的输入。可以从 PDF 或纯文本开始：

```bash
python s0_prepare_data.py --text /path/to/source.txt \
  --work data/my-work --episodes 20
python s1_diffuse.py --work data/my-work --only 1 --force
```

先检查分集结果和第一份故事概要。自动切分只是辅助，需要确认边界适合你的材料。检查或调整 `prompts/diffuse_heavy.md` 后，再生成完整输入：

```bash
python s1_diffuse.py --work data/my-work --noise heavy --force
```

`heavy` 生成精简的故事概要，`light` 保留更多叙述细节。程序会缓存各章结果；修改提示词后，用 `--force` 刷新缓存。`--only` 会写入所选章节的缓存并打印结果，但不会替换拼接后的 `story.md`。

## 同时训练多部作品

分别准备各部作品，然后重复传入 `--work`：

```bash
python s5_train.py \
  --work data/work-a --work data/work-b \
  --run-id two-works --steps 4 --episodes-per-step 5 \
  --epochs 3 --workers 4 --group-size 4
```

每一步先用当前技能库重建选定集数，再让比较智能体阅读生成剧本与人类原作。随后，程序按作品分组归并反馈，各组依次更新同一个技能库。只有一部作品的分组直接使用该作品的差异报告。每次完成的技能库更新都有独立的 Git 提交。

`--workers` 控制作品级任务的并发数，`--group-size` 控制每次技能更新汇总多少部作品，两者默认都是 4。`--group-size 0` 将全部作品放在同一组。生成概要的脚本另有 `--workers` 参数，默认是 8。

中断后用**同一条命令**继续，程序会检查产物并跳过已完成阶段。更换实验设置、提示词或输入时，请使用新的 `--run-id`。每次训练会保存当时的概要副本，续跑时若发现输入改变，会拒绝继续。

## 技能库

训练得到的是一组 Markdown 规则卡片，它们有独立的 Git 历史：

```text
memory/
├── 00_general_rules/     通用写作规则
├── 01_craft_elements/    对话、悬念、动作等具体技巧
└── 02_genre_specifics/   只在特定类型中适用的规则
```

每张卡片先写 YAML 格式的 `description` 字段，再写 `## Rules` 正文。前者说明**何时使用**，后者说明**如何做**。写作智能体被要求阅读通用规则，再选择适用的技巧和类型规则。程序记录它实际打开了哪些文件，为后续判断哪些规则有帮助、哪些需要修改提供依据。

更新智能体可以保留有效规则、纠正误导规则、补充缺失规则，或合并重复规则。格式检查器限制卡片结构和长度，默认每张最多 50 行、正文 4,800 字符、描述 800 字符，也会拒绝特定的集数引用和“模型与人类对比”表述模式。具体检查见 [`skilltrain/memory.py`](../skilltrain/memory.py)。

格式检查会作为提交前检查安装在技能库中。只有检查通过、存在提交且工作区干净时，这次更新才被标记为完成。

```bash
git -C runs/demo/memory log --oneline
git -C runs/demo/memory show HEAD
```

## 查看训练记录

```text
runs/demo/
├── config.json
├── memory/                         技能卡片及其 Git 历史
├── input/example.md                本次训练使用的输入
├── loss/epoch_00/step_00/
│   ├── example.md                  与人类参考剧本的差异报告
│   └── summary_g01.md              多作品分组的归并报告
└── epoch_00/step_00/
    ├── example/
    │   ├── scripts/ep01.txt ...    重建的剧本
    │   ├── forward_prompt.md
    │   ├── forward.jsonl
    │   ├── forward_trajectory.md
    │   └── forward_reads.txt
    └── backward/g01/
        ├── batch.json
        ├── backward_prompt.md
        ├── backward.jsonl
        ├── backward_trajectory.md
        ├── memory_before/
        ├── memory_after/
        ├── memory.patch
        ├── lint_report.txt
        └── commit.txt
```

差异报告包含人类原作的信息，因此放在写作步骤目录之外。每次写作后，程序会检查已记录的文件读取轨迹；如果发现读取了人类参考剧本或差异报告目录，就判定失败。这种轨迹检查并不是操作系统级别的隔离。

想追查某条规则为什么写错，可以从 `memory.patch` 找到对应的差异报告、更新过程记录，以及写作时实际读取的规则。`commit.txt` 是续跑时判断技能更新已经完成的标记。

## 单独运行各个阶段

下面使用快速开始中生成的技能库，产物放在独立的 `runs/manual/` 目录。与完整训练入口不同，单独运行时每次都会重跑相应阶段：

```bash
mkdir -p runs/manual
python s2_forward.py --work data/example --pool runs/demo/memory \
  --out runs/manual/forward --first 1 --last 5
python s3_loss.py --work data/example --scripts runs/manual/forward/scripts \
  --out runs/manual/loss.md --first 1 --last 5
```

若要更新技能库，创建 `runs/manual/batch.json`，将下面的 `/absolute/path/to/skill-training` 替换为仓库的绝对路径：

```json
[
  {
    "work": "example",
    "first": 1,
    "last": 5,
    "loss_report": "/absolute/path/to/skill-training/runs/manual/loss.md",
    "reads": "/absolute/path/to/skill-training/runs/manual/forward/forward_reads.txt",
    "trajectory": "/absolute/path/to/skill-training/runs/manual/forward/forward_trajectory.md"
  }
]
```

然后运行更新。注意，这会**修改 demo 的技能库**：

```bash
python s4_backward.py --pool runs/demo/memory \
  --batch runs/manual/batch.json --out runs/manual/backward
```

多作品批次中，每部作品添加一条记录。单独运行更新命令时，会直接使用批次中的差异报告；也可以通过 `--summary /path/to/summary.md` 传入已有归并报告。正常训练时，`s5_train.py` 会自动准备批次，并对多作品分组归并反馈。

## 对比持续更新与固定技能库

要单独观察“继续更新技能库”带来的效果，两组应使用**同一份初始技能库**、相同输入、模型和提示词，并使用不同运行名称。下面的 `runs/seed/memory` 是已有技能库，两次运行都不会修改它：

```bash
python s5_train.py --work data/example --run-id updating \
  --steps 4 --episodes-per-step 5 --init-pool runs/seed/memory

python s5_train.py --work data/example --run-id frozen \
  --steps 4 --episodes-per-step 5 --init-pool runs/seed/memory --no-backward
```

第一组复制初始技能库并持续更新自己的副本，第二组保持自己的副本不变。如果两组都去掉 `--init-pool`，对比的就是“从空库开始学习”与“始终使用空库”。从空库开始训练，再拿最终技能库做固定对照，是另一种比较，因为两组起点不同。

如果要判断能否推广到新材料，需要在未参与训练的材料上评估。训练样本上的差异报告本身不能证明这种提升。示例流程不包含论文使用的专有评测语料。

## 提示词与任务适配

| 模板 | 用途 |
| :--- | :--- |
| [`diffuse_heavy.md`](../prompts/diffuse_heavy.md) | 去掉剧本创作细节，保留精简概要。 |
| [`diffuse_light.md`](../prompts/diffuse_light.md) | 生成保留更多细节的叙述文本。 |
| [`forward.md`](../prompts/forward.md) | 利用技能库重建剧本。 |
| [`loss.md`](../prompts/loss.md) | 比较生成剧本与人类剧本。 |
| [`reduce.md`](../prompts/reduce.md) | 归并多部作品的反馈。 |
| [`backward.md`](../prompts/backward.md) | 根据反馈修改技能库。 |
| [`memory_policy.md`](../prompts/memory_policy.md) | 规定卡片格式与更新操作。 |

当前实现面向剧本。换到其他任务时，除了提示词，还可能需要修改数据解析和输出检查，包括 `epNN.txt` 文件约定。本次发布没有评估其他领域。

## 配置与运行开销

每个入口脚本都可以用 `--help` 查看完整选项。`--model` 原样传给 Claude Code；省略时由该命令行工具决定模型。身份认证同样使用现有的命令行登录状态及环境配置。

| 环境变量 | 默认值 | 含义 |
| :--- | :--- | :--- |
| `SKILLTRAIN_SETTING_SOURCES` | 空 | 要加载的命令行设置层；空值表示不加载这些设置层。 |
| `SKILLTRAIN_API_TIMEOUT_MS` | `600000` | 单次模型请求超时时间，单位为毫秒。 |
| `SKILLTRAIN_MAX_LINES` | `50` | 每张卡片的最大行数。 |
| `SKILLTRAIN_MAX_BODY_CHARS` | `4800` | 卡片正文的最大字符数。 |
| `SKILLTRAIN_MAX_DESCRIPTION_CHARS` | `800` | 卡片描述的最大字符数。 |

设置层列表为空，并不代表所有个人指令来源都一定被排除。运行器还会关闭子进程中的 Claude Code 自动记忆。遇到行为异常时，可以检查保存的提示词和执行记录。

时间和费用取决于模型、作品数量、集长、重试次数及工具交互轮次。一次命令行调用可能包含多次模型请求，不能直接拿调用次数估算费用。智能体使用 `--dangerously-skip-permissions` 运行，相关说明见快速开始。
