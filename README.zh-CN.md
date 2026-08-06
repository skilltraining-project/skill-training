# memory-sgd

**把一堆 Markdown 笔记当参数，对它做梯度下降，训练 agent 的"手艺"。**

[English](README.md) · [中文](README.zh-CN.md)

全程不碰模型权重。可训练参数就是一堆 `.md` 文件，agent 干活前会去读它们。
所谓梯度，就是这些文件上的一次 `git diff`。

```
forward   agent 只靠自己的笔记写东西
loss      拿它写的和专业编剧写的对着比
backward  另一个 agent 读对比报告，动手改笔记
```

这么循环下去，笔记会越来越好。每一步训练都记在 `git log` 里，可以逐条读。

---

## 它解决什么问题

假设你想让模型像职业编剧那样写剧本。微调需要成对的数据：一个输入，和它该产出的那份剧本。
可这个数据集根本不存在——剧本有的是，但产生这些剧本的那份"输入"从来没人留下来过。

图像扩散模型当年遇到过一模一样的困境，它的解法是反着来：你收集不到（噪声，图像）配对，
但你可以拿一张真图去毁掉它，配对就白送到手了。在"毁掉"这件事上训练，得到的就是能把它复原的模型。

同样的招数用在剧本上。拿一份真剧本，把编剧的贡献全剥掉：台词删掉，调度删掉，分场删掉。
剩下的是一段干巴巴的散文梗概——事情都发生了，但没人把它拍成戏。

这段梗概和原剧本，就是一对训练数据，而且零成本。把梗概喂进去，要一份剧本回来，
再跟原稿比。两者之间的差距，恰恰就是刚才被剥掉的那层手艺。学会把这个差距补上，就是学会了这门手艺。

## 三个 agent 凑成一次 SGD

| | 神经网络里 | 这里 |
|---|---|---|
| 参数 | 权重张量 | 一个装满 Markdown 规则的文件夹 |
| forward | 跑一遍网络 | agent 靠笔记写一集剧本 |
| loss | 跟标签比 | 跟人类剧本比 |
| backward | 反向传播 | agent 读对比报告，动手改笔记 |
| 优化器更新 | `w -= lr * grad` | 在笔记上提一个 git commit |
| batch | 一步喂多个样本 | 一步同时跑多个剧本 |
| epoch | 数据过一遍 | 全部剧本过一遍 |

forward 那个 agent 是**闭卷**的。它只看得到加了噪的梗概和自己的笔记，
从头到尾看不到人类剧本，所以抄不了。能让它写得更好的东西，只可能来自笔记里写了什么。

loss 是一份**文档**，不是一个数字。数字只告诉你差多远，文档告诉你该改什么——
后者才是优化器真正需要的东西。

backward 是唯一有权写笔记的角色。它拿到的除了 loss 报告，还有每份报告配套的
**read trace**：forward 当时到底打开了哪几个文件。这是信用分配能成立的前提——
一条规则只能为它"在场"的那份剧本负责。

它有四个动作，其实就是梯度能有的几种方向：

- **强化**：这条规则起了作用，通常什么都不用改
- **修正**：这条规则误导了，那就缩小它的适用范围，或者把写法改松
- **新建**：出现了池子里没人管的问题
- **合并**：两条规则漂移成了近义词

改完提交。这个 commit 就是一步。

## 快速开始

需要 Python 3.10+ 和登录好的 [Claude Code](https://claude.com/claude-code) CLI。
没了。没有任何 Python 依赖。在 macOS 和 Linux 上开发和测试，假设有 POSIX shell。

```bash
git clone https://github.com/Mor-Li/memory-sgd && cd memory-sgd
python3 -m unittest discover tests      # 离线自检，不调 API
```

拿一份剧本，切成集：

```bash
bash data/get_example.sh               # 一份 CC BY-SA 许可的剧本
python3 s0_prepare_data.py --pdf data/example/source.pdf --episodes 20
```

把它毁成训练输入。这是唯一一次性把全量数据过一遍的步骤，每份剧本只花一次钱：

```bash
python3 s1_diffuse.py --work data/example --only 1 --force   # 先毁一章打印出来看
python3 s1_diffuse.py --work data/example --noise heavy      # 满意了再跑全量
```

跑全量前先把这一章读一遍。这一步毁到什么程度，决定了后面所有环节的难度，
也是最值得手调的一个旋钮。它在 `prompts/diffuse_heavy.md` 里。

正式训练：

```bash
python3 s5_train.py --work data/example --steps 4 --episodes-per-step 5
```

看笔记是怎么长出来的：

```bash
git -C runs/*/memory log --oneline
git -C runs/*/memory show HEAD
```

想单独盯某一环，每个脚本都能自己跑：

```bash
python3 s2_forward.py  --work data/example --pool runs/<id>/memory \
                      --out /tmp/fw --first 1 --last 5
python3 s3_loss.py     --work data/example --scripts /tmp/fw/scripts \
                      --out /tmp/loss.md --first 1 --last 5
python3 s4_backward.py --pool runs/<id>/memory --batch /tmp/batch.json --out /tmp/bw
```

那个 `batch.json` 平时是 `s5_train.py` 自动写的。想手写的话，一个 work 一条：

```json
[{"work": "example", "first": 1, "last": 5,
  "loss_report": "/abs/runs/<id>/loss/epoch_00/step_00/example.md",
  "reads": "/abs/runs/<id>/epoch_00/step_00/example/forward_reads.txt",
  "trajectory": "/abs/runs/<id>/epoch_00/step_00/example/forward_trajectory.md"}]
```

重跑 `s5_train.py`（参数不变）就是**续跑**。每一环自己检查产物在不在，
中断了再跑就接着上次的地方走。没有单独的进度文件，也就不存在进度文件跟实际状态对不上的问题。
上面那几条单环命令没有这套检查，每次都会真跑。

## 一个"参数"长什么样

一条规则一个文件。格式就这些：

```markdown
---
description: 两个角色吵架、谈判、坦白、隐瞒时使用。适合他们嘴上说一件事、心里是另一件事的场景。不适合纯粹交代信息的台词，比如报地址、说诊断结果。
---

## Rules
让角色把真实情绪绕道具体的小事上。别直接说"我在乎你"，让他们为椅子上的一件外套、
一杯凉了的咖啡、一个没接的电话发难。关系里的压力压在台词底下，不在台词表面。
```

这个上下分工是真在干活的。`description` 是 forward agent 决定"要不要打开这条"时
唯一看得到的东西，所以它必须写清边界。正文是打开之后才读的，所以不能再浪费篇幅重复边界。
这一点写反了，是池子失效最常见的原因：description 写成了"这条规则教什么"而不是
"什么时候用它"，于是条条看起来都相关，agent 要么全读要么全不读。

池子只有三个文件夹，就三个：

```
memory/
  00_general_rules/     这门媒介是什么、什么叫好。每次必读。
  01_craft_elements/    台词怎么写、钩子怎么埋、动作线怎么写。按需读。
  02_genre_specifics/   只在某个题材内成立的规律。题材对上了才读。
```

有个 linter 卡形状：只能有一个 `description` 字段，正文只能有一个 `## Rules` 标题，
最多 50 行，不许出现集数，不许写"模型写成 X、人类写成 Y"。
它挂在池子的 git pre-commit hook 上，所以优化器就算想提交一条畸形规则也提交不进去。

那几个尺寸上限不是为了整洁。forward 每一趟都会把所有 description 读一遍，
池子无限膨胀就等于无法路由。一条规则涨过头时，优化器只有两条路：压缩它，
或者按更窄的边界拆成两条——这两件事都是池子在变得更有条理，而不是单纯变大。

## 一步训练具体长什么样

来自示例剧本的第一个训练 step。当时池子是空的，写手全凭自己的直觉写，
loss 报告回来时说了一堆，其中一条是：

> Human: abstract but three words long. Model: concrete but forty words long,
> with a metaphor attached.
>
> （人类：抽象，但只有三个词。模型：具体，但四十个词，还挂了个比喻。）

优化器读完报告，判断这个差异出现得够频繁、值得写成规则而不是当个例放过，
于是提交了一条新条目。其中一段：

```markdown
## Rules
Count speeches against the beat. Name what the exchange settles, then find the
fewest lines that settle it. A beat running twelve or fifteen speeches is very
often three speeches with padding between them.

Do not volley. Splitting one thought into a rally of one- and two-word lines
feels like naturalism and reads as stalling. Give the character the whole
thought in one speech and move on.
```

这一步一共长出 8 条，分布在三个文件夹里，全部在 linter 的限额内，一次 commit 提交。
下一步写手会看到它们的 description，然后按当前要写的内容挑着打开。

这条规则没有人写。那句观察也没有人写。全程只提供了一份剧本，和一套毁掉它的办法。

## 一次 run 留下什么

```
runs/<run-id>/
  config.json                       这次是用什么参数起的
  memory/                           池子本体，自带 git 历史
  input/example.md                  加噪后的故事，这次 run 看到的那一份
  loss/epoch_00/step_00/example.md  训练信号
  epoch_00/step_00/
    example/
      scripts/ep01.txt ...          agent 写出来的剧本
      forward_prompt.md             它当时被告知的一切
      forward.jsonl                 原始会话
      forward_trajectory.md         它干的每一件事，可读版
      forward_reads.txt             写的时候哪几条规则是打开的
    backward/
      batch.json                    优化器拿到了什么
      backward_trajectory.md        它的推理过程
      memory_before/ memory_after/  这一步前后的池子
      memory.patch                  梯度，以 diff 的形式
      commit.txt                    所有检查都过了才会写
```

loss 报告单独放一个目录，不跟剧本挨着。因为报告里会引用人类原稿，
而 forward agent 干活的位置就在 step 目录里——把两者隔开，
第二个 epoch 才不会在隔壁翻到第一个 epoch 的标准答案。
每次 forward 跑完还会拿 read trace 去比对那个目录和 `data/<work>/human/`，
一旦真读了，这一步直接判失败，而不是悄悄拿个好成绩。

这里没有一样东西是"事后总结"，全都是当场发生的原始记录。
某一步产出了一条烂规则，你可以回去读导致它的 loss 报告、支撑它的 trace、以及最终落地的那个 diff。

优化器和"这一步算完成"之间隔着三道关：linter 过、确实有一个 commit、工作区干净。
三道全过才写 `commit.txt`，而续跑时也正是靠这个文件判断这步做完了没有。
半成品永远不会被当成做完。

## 它真的在学吗

同样的东西跑两遍，一遍把池子冻住：

```bash
python3 s5_train.py --work data/example --steps 4 --episodes-per-step 5

python3 s5_train.py --work data/example --steps 4 --episodes-per-step 5 \
    --no-backward --init-pool runs/<训练好的run>/memory
```

第二次跑用的是第一次训练出来的池子，冻在它当时学到的状态，全程不更新。
同一个写手、同样的故事、同样的 prompt，唯一的区别是笔记还能不能继续变。
拿两边最后一步的 loss 报告对着看。

不加 `--init-pool` 是另一个更粗的对照：完全没笔记 vs 会进化的笔记。
那个回答的是"笔记有没有用"，不是"这个循环能不能把笔记变好"。

跑的过程里有两件事值得盯：

- **read trace**。一开始 agent 几乎什么都打开，因为 description 写得含糊，条条看着都相关。
  池子理顺之后，它打开的会越来越少、越来越准。
- **池子的动作构成**。前期基本都是"新建"，后期会转向"修正"和"合并"。
  跑了很多步还在一味新建的池子，是在攒东西，不是在学东西。

## 换成写别的

这套 pipeline 根本不知道自己在写剧本。那件事完全活在 `prompts/` 里，六个 markdown 文件：

```
prompts/
  diffuse_heavy.md    怎么毁掉一个样本。任务的定义就在这里。
  diffuse_light.md    同上，毁得轻一点
  forward.md          怎么写，以及写成什么格式
  loss.md             什么样的差异值得报出来
  backward.md         怎么把差异变成对笔记的修改
  memory_policy.md    一条规则是什么，以及那四个动作
```

想训练别的，就换掉"怎么毁"和"什么格式"这两件事。
只要你能拿到这件事的好样本、并且能机械地把其中的手艺剥掉，你就有了训练集。
法律文书、技术文档、产品文案、bug 报告、code review 意见，都适用。
反过来，如果手艺本身在产物里读不出来，或者你根本拿不到好样本，就不适合。

## 花多少钱，以及它能碰什么

把 20 集的示例完整跑一遍，大约 32 次模型调用：20 次用来加噪（每份剧本只花一次，
有缓存），此后每个训练 step 3 次——写、比、改。加噪和 loss 是单次纯文本调用；
forward 和 backward 是带工具的 agent，时间和钱主要花在这两个上。

agent 是带 `--dangerously-skip-permissions` 跑的，这也是这个循环能无人值守的原因。
按设计它只写 run 目录和 memory 池，backward 会在池子里跑 git。
但没有任何东西在强制这个边界，所以请在你愿意放手给 agent 的环境里跑。

## 配置

能配的基本都是命令行参数。少数不常动的走环境变量：

| 变量 | 默认 | 作用 |
|---|---|---|
| `MEMSGD_SETTING_SOURCES` | 空 | agent 加载哪几层 CLI 配置。留空 = 你自己的 `CLAUDE.md` 进不去实验 |
| `MEMSGD_API_TIMEOUT_MS` | `600000` | 单次请求超时，模型慢就调大 |
| `MEMSGD_MAX_LINES` | `50` | 单条规则行数上限 |
| `MEMSGD_MAX_BODY_CHARS` | `4800` | 单条规则正文字符上限 |

选模型用 `--model`，直接透传给 CLI；不传就用你 CLI 自己的默认。
任何 Anthropic 兼容网关都能用，走 CLI 自己的 `ANTHROPIC_BASE_URL` 和
`ANTHROPIC_AUTH_TOKEN` 即可。本项目自己从不读 API key。

## 这东西哪来的

它是一套更大的私有系统的开源提炼版——那套系统在专有语料上训练剧本 agent。
机制是同一套。数据、视频生产链路、评测 harness 都不在这里。
在这里的是真正值得复用的那部分：这个循环、这个池子，
以及"写作这件事也能做梯度下降"这个想法本身。

## 许可

MIT。
