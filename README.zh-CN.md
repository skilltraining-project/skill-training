<p align="center">
  <img src="docs/assets/logo.png" width="88" height="88" alt="Skill Training 标志">
</p>

<h1 align="center">Skill Training</h1>

<p align="center">学习专业手艺，保持模型权重不变。</p>

<p align="center">
  <a href="https://skilltraining-project.github.io/">项目主页</a> ·
  <a href="https://skilltraining-project.github.io/assets/paper.pdf?v=473e0fa1818b">PDF</a> ·
  <a href="https://arxiv.org/abs/2607.27557">arXiv</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="docs/guide.zh-CN.md">使用指南</a>
</p>

<p align="center">
  <a href="https://github.com/skilltraining-project/skill-training/actions/workflows/test.yml"><img src="https://github.com/skilltraining-project/skill-training/actions/workflows/test.yml/badge.svg" alt="离线测试"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/Python-3.10%2B-3e55a5?style=flat" alt="Python 3.10 及以上"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-3e55a5?style=flat" alt="MIT 许可"></a>
  <a href="https://github.com/skilltraining-project/skill-training/stargazers"><img src="https://img.shields.io/github/stars/skilltraining-project/skill-training?style=flat&color=3e55a5" alt="GitHub 收藏数"></a>
</p>

<p align="center"><a href="README.md">English</a> · 简体中文</p>

## 项目介绍

专业作品里包含许多难以直接写成指令的经验。**Skill Training 从已有的人类作品中学习这些经验**，不更新模型权重，也不需要额外收集人类标注或外部奖励。

做法很直接：先把专业剧本压缩成故事大纲，让智能体尝试重建剧本，再从它与原稿的差距中学习。训练得到的是一套外部**技能库**，由智能体写作前会阅读的 Markdown 文件组成。每次修改都保存在 Git 历史里，因此学到了什么、怎么改过，都可以查看、编辑和复用。

本仓库是论文 **Skill Training with Corruption and Reconstruction Loop** 的参考实现。

**Mo Li · Zixin Yin · Qihao Wu · Ting Cao · Yunxin Liu · Heung-Yeung Shum**<br>
清华大学 · 上海人工智能实验室 · 香港科技大学 · 小冰

<p align="center">
  <a href="https://skilltraining-project.github.io/#method"><img src="docs/assets/framework.png" width="960" alt="把人类剧本压缩为大纲，借助技能库重建剧本，与原稿比较，再更新相关技能，形成循环。"></a>
</p>

| 环节 | 做什么 | 运行命令 |
| :--- | :--- | :--- |
| **加噪** | 保留故事大纲，去掉对白、动作和节奏等写作细节。 | [`python -m skilltrain diffuse`](skilltrain/workflows/s1_diffuse.py) |
| **重建** | 读取相关技能卡片，从大纲生成剧本。 | [`python -m skilltrain forward`](skilltrain/workflows/s2_forward.py) |
| **比较** | 对照生成稿与人类原稿，用文字指出差距。 | [`python -m skilltrain loss`](skilltrain/workflows/s3_loss.py) |
| **更新** | 根据反馈修改技能库。 | [`python -m skilltrain backward`](skilltrain/workflows/s4_backward.py) |

[`python -m skilltrain prepare`](skilltrain/workflows/s0_prepare_data.py) 负责准备数据；[`python -m skilltrain train`](skilltrain/workflows/s5_train.py) 串起训练循环、保存过程记录，并支持中断后继续运行。

## 论文实验结果

主实验用 **20 部专业短剧作品**训练，在**六部未见作品的 385 集**上评估 Claude Sonnet 4.6。论文的配对自助抽样分析表明，六项有明确优化方向的指标均较空技能库显著改善。

| 写作行为 | 空技能库 | 训练后技能库 | 人类原稿 |
| :--- | ---: | ---: | ---: |
| 每集不可拍摄的动作描述行数 ↓ | 1.2 | **0.2** | 0.4 |
| 每集刺激词数量 ↑ | 3.3 | **6.3** | 9.2 |
| 每千词剧情冲突数量 ↑ | 2.10 | **3.69** | 3.47 |
| 硬切结尾比例 ↑ | 34% | **67%** | 62% |
| 冷开场比例 ↑ | 52% | **74%** | 59% |
| 道具参与情节比例 ↑ | 46% | **58%** | 57% |

这些指标描述具体写作行为，不等同于整体质量。另一项盲评中，训练版在 **75 次判断中获胜 49 次**，空库版获胜 17 次，平局 9 次。评估包含 15 对剧集和五位读者，其中三位是外部短剧从业者，两位是论文作者。

### 随着训练，技能如何变化

在 174 次技能更新中，结构分数在第一轮训练快速提高，第三轮趋于稳定，接近 0.75。与此同时，技能库的更新从大量新增规则，逐渐转向修改已有规则。

<p align="center">
  <a href="https://skilltraining-project.github.io/#training"><img src="docs/assets/training-curve.png" width="960" alt="训练曲线：留出集上的结构分数随三轮训练提高，技能库逐渐从新增规则转向修改已有规则。"></a>
</p>

每个训练快照都在相同的 **180 集留出剧本**上评估，即六部未见作品各取前 30 集。结构分数由四项标准化的结构指标取平均得到，空库分数为零。阴影表示 95% 自助抽样区间，虚线为人类原稿参照。

<details>
<summary><strong>跨模型迁移：一个模型学到的技能，也能帮助另一个模型</strong></summary>

Sonnet 学到的技能库也能改善 Kimi K2.6 和 Claude Opus 4.8。使用 Sonnet 的技能库时，Opus 在六项有方向指标中的五项上显著优于使用自己的技能库，硬切结尾是例外。这组实验中的技能库均用**五部作品**训练。

<p align="center">
  <img src="docs/assets/transfer.png" width="960" alt="Sonnet 4.6、Kimi K2.6 和 Opus 4.8 在空库、迁入 Sonnet 技能库和各自技能库下的实验结果。">
</p>

</details>

以上图表与数字来自[论文](https://skilltraining-project.github.io/assets/paper.pdf?v=473e0fa1818b)。本仓库提供精简的参考实现和一份开放许可示例，不包含论文使用的专有短剧语料。下面的示例用于跑通流程，不能单独复现论文的完整实验。

## 快速开始

### 1. 准备环境

需要 Python 3.10+、Git，以及已安装并完成认证的 [Claude Code](https://claude.com/claude-code) 命令行工具。框架**只使用 Python 标准库**，无需安装第三方 Python 包。在仓库根目录运行以下命令，不需要安装项目本身；这里用 [uv](https://docs.astral.sh/uv/) 创建本地环境。

```bash
git clone https://github.com/skilltraining-project/skill-training
cd skill-training
uv venv --python 3.12
source .venv/bin/activate

python -m unittest discover tests
```

离线检查不调用模型。从 PDF 提取文字需要 `pdftotext`：macOS 可运行 `brew install poppler`，Ubuntu 可运行 `sudo apt install poppler-utils`。示例流程还使用 Bash、curl 和系统 `diff` 命令。支持 macOS 和 Linux。

### 2. 准备示例，先检查一份大纲

```bash
bash data/get_example.sh
python -m skilltrain prepare --pdf data/example/source.pdf --episodes 20
python -m skilltrain diffuse --work data/example --only 1 --force
```

示例剧本为 **Valkaama**，采用 CC BY-SA 3.0 许可，详见[数据来源与署名](data/README.md)。先检查切分后的剧集和打印出来的大纲。如需调整，修改 [`prompts/diffuse_heavy.md`](prompts/diffuse_heavy.md)，再生成完整输入：

```bash
python -m skilltrain diffuse --work data/example --noise heavy --force
```

`--only 1 --force` 会更新单章缓存并打印结果，但不会替换完整的 `story.md`。全量命令加上 `--force`，可以让修改后的提示词也应用到此前已缓存的章节。

### 3. 开始训练，查看学到的技能

```bash
python -m skilltrain train --work data/example \
  --run-id demo --steps 4 --episodes-per-step 5

git -C runs/demo/memory log --oneline
git -C runs/demo/memory show HEAD
```

使用相同参数重跑训练命令即可续跑。新实验请换一个 `--run-id`。训练通过 Claude Code 调用模型，沿用它的认证与使用额度。智能体以 `--dangerously-skip-permissions` 运行；代码约定的工作目录并不是安全沙箱。

多作品训练、单独运行各环节、冻结技能库的对照实验，以及配置说明，都在**[使用指南](docs/guide.zh-CN.md)**里。

## 仓库结构

```text
skill-training/
├── skilltrain/              训练包与共用工具
│   ├── __main__.py         统一命令入口
│   ├── workflows/          按顺序编号的流程实现
│   └── …                   智能体调用、数据、记忆与轨迹工具
├── prompts/                七份可编辑的任务与训练模板
├── tests/                  离线检查
├── data/                   示例下载脚本与数据说明
├── docs/                   使用指南与论文图片
└── pyproject.toml          项目配置
```

每次训练的产物保存在 `runs/<run-id>/`：生成的剧本、文字反馈、智能体的文件读取记录，以及自带 Git 历史的技能库。每个技能更新小步都保留修改前后的技能库、文件差异和完成后的提交记录。

**训练产物是可以直接阅读的文字。** 技能按通用规则、写作技巧和题材规则分类。格式检查器会限制每张卡片的长度，并在提交前检查内容格式。详见[技能卡片格式与训练产物](docs/guide.zh-CN.md#技能库)。

## Star 历史

<p align="center">
  <a href="https://www.star-history.com/#skilltraining-project/skill-training&Date"><img src="https://api.star-history.com/svg?repos=skilltraining-project/skill-training&type=Date" width="720" alt="skilltraining-project/skill-training 的 GitHub 收藏历史"></a>
</p>

## 引用

```bibtex
@misc{li2026skilltraining,
  title         = {Skill Training with Corruption and Reconstruction Loop},
  author        = {Li, Mo and Yin, Zixin and Wu, Qihao and Cao, Ting
                   and Liu, Yunxin and Shum, Heung-Yeung},
  year          = {2026},
  eprint        = {2607.27557},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2607.27557}
}
```

## 联系与许可

使用问题和缺陷反馈可以[提交 Issue](https://github.com/skilltraining-project/skill-training/issues)。研究交流请联系 **Mo Li**：[limo.research@gmail.com](mailto:limo.research@gmail.com)。

代码采用 **[MIT 许可](LICENSE)**。下载的示例剧本单独采用 [CC BY-SA 3.0 许可](data/README.md)，请保留对应署名。

## 相关工作

[Learning to Commit](https://github.com/LearningToCommit/LearningToCommit) 从历史代码提交中学习项目特有的编程技能，同样不更新模型权重。
