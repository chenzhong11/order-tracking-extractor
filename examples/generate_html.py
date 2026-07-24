"""生成 Kami 风格 HTML 技术报告。"""

import os
import base64

OUT = "docs"

def img_to_base64(path):
    """将图片转为 base64 data URI。"""
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return f"data:image/png;base64,{data}"

def generate_html():
    fig1 = img_to_base64("docs/images/fig1_signal_validation.png")
    fig2 = img_to_base64("docs/images/fig2_order_tracking_validation.png")
    fig3 = img_to_base64("docs/images/fig3_threshold_comparison.png")
    fig4 = img_to_base64("docs/images/fig4_diagnostic_report.png")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>柱塞泵故障诊断算法技术报告 v7.23</title>
<style>
@font-face {{
  font-family: "TsangerJinKai02";
  src: url("https://cdn.jsdelivr.net/gh/tw93/Kami@main/assets/fonts/TsangerJinKai02-W04.ttf") format("truetype");
  font-weight: 400; font-style: normal;
}}
@font-face {{
  font-family: "TsangerJinKai02";
  src: url("https://cdn.jsdelivr.net/gh/tw93/Kami@main/assets/fonts/TsangerJinKai02-W05.ttf") format("truetype");
  font-weight: 500; font-style: normal;
}}
@font-face {{
  font-family: "JetBrains Mono";
  src: url("https://cdn.jsdelivr.net/gh/JetBrains/JetBrainsMono/fonts/ttf/JetBrainsMono-Regular.ttf") format("truetype");
  font-weight: 400; font-style: normal;
}}

:root {{
  --parchment: #f5f4ed;
  --ivory: #faf9f5;
  --warm-sand: #e8e6dc;
  --near-black: #141413;
  --dark-warm: #3d3d3a;
  --olive: #504e49;
  --stone: #6b6a64;
  --brand: #1B365D;
  --brand-light: #2D5A8A;
  --border: #e8e6dc;
  --border-soft: #e5e3d8;
  --tag-bg: #E4ECF5;
  --serif: "TsangerJinKai02", "Source Han Serif SC", "Noto Serif CJK SC", "Songti SC", Georgia, serif;
  --mono: "JetBrains Mono", "SF Mono", Consolas, monospace;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}
@page {{ margin: 0; }}

body {{
  font-family: var(--serif);
  font-size: 10pt;
  font-weight: 400;
  line-height: 1.55;
  color: var(--near-black);
  background: var(--parchment);
  padding: 40pt 60pt;
  max-width: 900pt;
  margin: 0 auto;
}}

/* 标题 */
h1 {{
  font-size: 28pt;
  font-weight: 500;
  line-height: 1.15;
  color: var(--near-black);
  margin-bottom: 8pt;
}}
h1 .version {{
  font-size: 11pt;
  color: var(--stone);
  font-weight: 400;
  display: block;
  margin-top: 4pt;
}}

h2 {{
  font-size: 16pt;
  font-weight: 500;
  line-height: 1.25;
  color: var(--near-black);
  margin: 28pt 0 10pt 0;
  border-left: 2.5pt solid var(--brand);
  border-radius: 1.5pt;
  padding-left: 8pt;
}}

h3 {{
  font-size: 13pt;
  font-weight: 500;
  line-height: 1.3;
  color: var(--dark-warm);
  margin: 18pt 0 8pt 0;
}}

p {{ margin: 6pt 0; }}

/* 标签 */
.tag {{
  display: inline-block;
  background: var(--tag-bg);
  color: var(--brand);
  font-size: 9pt;
  font-weight: 600;
  padding: 1pt 6pt;
  border-radius: 2pt;
  letter-spacing: 0.4pt;
  margin-right: 3pt;
}}

/* 指标卡 */
.metric {{
  display: inline-flex;
  align-items: baseline;
  gap: 6pt;
  margin: 4pt 8pt 4pt 0;
}}
.metric-value {{
  font-size: 16pt;
  font-weight: 500;
  color: var(--brand);
  font-variant-numeric: tabular-nums;
}}
.metric-label {{
  font-size: 9pt;
  color: var(--olive);
}}

/* 表格 */
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 9pt;
  margin: 8pt 0;
}}
th {{
  text-align: left;
  font-weight: 500;
  color: var(--dark-warm);
  padding: 5pt 8pt;
  border-bottom: 1pt solid var(--border);
  background: var(--ivory);
}}
td {{
  padding: 4pt 8pt;
  border-bottom: 0.3pt solid var(--border-soft);
  vertical-align: top;
}}
tr:hover td {{ background: var(--ivory); }}

/* Callout */
.callout {{
  background: transparent;
  border-left: 1.8pt solid var(--brand);
  padding: 4pt 0 4pt 14pt;
  margin: 10pt 0;
  font-size: 10pt;
  line-height: 1.5;
  color: var(--olive);
}}
.callout .hl {{ color: var(--brand); font-weight: 500; }}

/* 引用块 */
blockquote {{
  border-left: 2pt solid var(--brand);
  padding: 4pt 0 4pt 14pt;
  color: var(--olive);
  line-height: 1.55;
  margin: 8pt 0;
}}

/* 代码 */
code {{
  font-family: var(--mono);
  font-size: 9pt;
  background: var(--ivory);
  padding: 1pt 4pt;
  border-radius: 2pt;
}}

/* 图片 */
.figure {{
  margin: 14pt 0;
  text-align: center;
}}
.figure img {{
  max-width: 100%;
  border: 0.5pt solid var(--border);
  border-radius: 3pt;
}}
.figure-caption {{
  font-size: 9pt;
  color: var(--stone);
  margin-top: 4pt;
  line-height: 1.45;
}}

/* 分隔线 */
hr {{
  border: none;
  border-top: 0.5pt solid var(--border);
  margin: 20pt 0;
}}

/* 列表 */
ul, ol {{ margin: 6pt 0 6pt 18pt; }}
li {{ margin-bottom: 3pt; }}

/* 封面 */
.cover {{
  text-align: center;
  padding: 60pt 0 40pt 0;
  border-bottom: 1pt solid var(--border);
  margin-bottom: 30pt;
}}
.cover .doc-type {{
  font-size: 9pt;
  font-weight: 600;
  color: var(--brand);
  letter-spacing: 1pt;
  text-transform: uppercase;
  margin-bottom: 12pt;
}}

/* 目录 */
.toc {{
  background: var(--ivory);
  border: 0.5pt solid var(--border);
  border-radius: 3pt;
  padding: 14pt 18pt;
  margin: 16pt 0;
}}
.toc-title {{
  font-size: 11pt;
  font-weight: 500;
  color: var(--brand);
  margin-bottom: 8pt;
}}
.toc a {{
  color: var(--near-black);
  text-decoration: none;
  display: block;
  padding: 2pt 0;
  font-size: 10pt;
}}
.toc a:hover {{ color: var(--brand); }}

/* 状态标签 */
.status-pass {{
  display: inline-block;
  background: #E8F5E9;
  color: #2E7D32;
  font-size: 9pt;
  font-weight: 600;
  padding: 1pt 6pt;
  border-radius: 2pt;
}}
.status-fail {{
  display: inline-block;
  background: #FFEBEE;
  color: #C62828;
  font-size: 9pt;
  font-weight: 600;
  padding: 1pt 6pt;
  border-radius: 2pt;
}}

/* 页脚 */
.footer {{
  margin-top: 40pt;
  padding-top: 12pt;
  border-top: 0.5pt solid var(--border);
  font-size: 9pt;
  color: var(--stone);
  text-align: center;
}}
</style>
</head>
<body>

<!-- 封面 -->
<div class="cover">
  <div class="doc-type">技术报告</div>
  <h1>柱塞泵故障诊断算法<br>技术报告<span class="version">v7.23 · order_tracking_v2 · 2026-07-24</span></h1>
  <div style="margin-top: 16pt;">
    <span class="tag">阶次分析</span>
    <span class="tag">特征提取</span>
    <span class="tag">故障诊断</span>
    <span class="tag">统计阈值</span>
  </div>
</div>

<!-- 目录 -->
<div class="toc">
  <div class="toc-title">目录</div>
  <a href="#sec1">1. 仿真信号有效性验证（白盒测试）</a>
  <a href="#sec2">2. 阶次分析算法有效性（COT vs TOT）</a>
  <a href="#sec3">3. 统计阈值对比验证</a>
  <a href="#sec4">4. 故障诊断综合报告（真实数据）</a>
  <a href="#sec5">5. 故障-信号映射表</a>
</div>

<!-- 第1节 -->
<h2 id="sec1">1. 仿真信号有效性验证</h2>

<blockquote>
  <strong>目的</strong>：用已知参数的合成信号，验证算法能否精确恢复特征频率。<br>
  <strong>方法</strong>：正常信号 = 转频脉动 + 柱塞频率脉动 + 噪声；故障信号 = 正常 + 指数衰减冲击脉冲串（周期 = 1/f<sub>p</sub>）
</blockquote>

<div class="figure">
  <img src="{fig1}" alt="仿真信号有效性验证">
  <div class="figure-caption">图1：合成信号白盒测试 — (a) 时域波形 (b) FFT频谱 (c) 包络谱 (d) TOT阶次谱</div>
</div>

<table>
  <tr><th>子图</th><th>验证内容</th><th>判定标准</th><th>结果</th></tr>
  <tr><td>(a) 时域波形</td><td>冲击脉冲是否可见</td><td>故障信号在 f<sub>p</sub> 周期位置出现尖峰</td><td><span class="status-pass">通过</span></td></tr>
  <tr><td>(b) FFT 频谱</td><td>f<sub>r</sub>, f<sub>p</sub>, 2f<sub>p</sub> 谱线是否准确</td><td>频率误差 &lt; 1%</td><td><span class="status-pass">通过</span></td></tr>
  <tr><td>(c) 包络谱</td><td>共振解调能否恢复 f<sub>p</sub></td><td>包络谱中 f<sub>p</sub> 幅值显著高于噪声底</td><td><span class="status-pass">通过</span></td></tr>
  <tr><td>(d) TOT 阶次谱</td><td>7阶和14阶是否突出</td><td>故障时 7 阶和 14 阶幅值显著增大</td><td><span class="status-pass">通过</span></td></tr>
</table>

<div class="callout">
  <span class="hl">结论</span>：合成信号白盒测试通过 — 算法能精确恢复 f<sub>r</sub>, f<sub>p</sub>, 2f<sub>p</sub>，包络谱能检出 f<sub>p</sub> 冲击重复频率，TOT 阶次谱能定位 7 阶和 14 阶。
</div>

<hr>

<!-- 第2节 -->
<h2 id="sec2">2. 阶次分析算法有效性（COT vs TOT）</h2>

<blockquote>
  <strong>目的</strong>：对比 COT（无转速计）和 TOT（有转速计）两种阶次分析方法的精度和故障检出能力。<br>
  <strong>数据</strong>：真实柱塞泵正常/故障振动信号（X轴，20kHz，7柱塞，1480RPM）
</blockquote>

<div class="figure">
  <img src="{fig2}" alt="阶次分析算法有效性">
  <div class="figure-caption">图2：COT vs TOT 对比 — (a) 转频估计 (b) 阶次幅值 (c) COT检出比值 (d) TOT检出比值</div>
</div>

<table>
  <tr><th>指标</th><th>COT</th><th>TOT</th><th>结论</th></tr>
  <tr><td>转频估计误差</td><td>1.46%</td><td>0.00%</td><td>TOT 更精确</td></tr>
  <tr><td>7阶检出比值</td><td>3.11x</td><td>3.00x</td><td>两者均可检出</td></tr>
  <tr><td>14阶检出比值</td><td>6.12x</td><td>3.00x</td><td>COT 比值更高但不稳定</td></tr>
  <tr><td>稳定性</td><td>受 STFT 窗长影响</td><td>稳定</td><td>TOT 更优</td></tr>
</table>

<div class="callout">
  <span class="hl">结论</span>：TOT 优于 COT — 转频精度更高、阶次比值更稳定。COT 在无转速信号时仍可用，但建议窗长 &ge; 2048。
</div>

<hr>

<!-- 第3节 -->
<h2 id="sec3">3. 统计阈值对比验证</h2>

<blockquote>
  <strong>目的</strong>：对比固定比值阈值、3&sigma; 统计阈值、P95 统计阈值三种判定方式的检出效果。<br>
  <strong>方法</strong>：从正常信号滑动窗口切分 194 段伪样本，计算 106 个特征的统计阈值
</blockquote>

<div class="figure">
  <img src="{fig3}" alt="统计阈值对比">
  <div class="figure-caption">图3：三种阈值模式对比 — (a) 固定比值 (b) 3&sigma; (c) P95</div>
</div>

<table>
  <tr><th>故障类型</th><th>固定比值</th><th>3&sigma;</th><th>P95</th></tr>
  <tr><td>松靴/滑靴脱落</td><td><span class="status-pass">2.0</span></td><td><span class="status-pass">0.5</span></td><td><span class="status-pass">0.5</span></td></tr>
  <tr><td>配流盘磨损</td><td><span class="status-pass">2.0</span></td><td><span class="status-fail">0.5</span></td><td><span class="status-fail">0.5</span></td></tr>
  <tr><td>柱塞-缸孔磨损</td><td><span class="status-pass">2.0</span></td><td><span class="status-fail">0.0</span></td><td><span class="status-fail">0.0</span></td></tr>
  <tr><td>斜盘磨损</td><td><span class="status-fail">0.0</span></td><td><span class="status-fail">0.0</span></td><td><span class="status-fail">0.0</span></td></tr>
  <tr><td>轴承外圈故障</td><td><span class="status-pass">1.0</span></td><td><span class="status-fail">0.0</span></td><td><span class="status-fail">0.0</span></td></tr>
  <tr><td>轴承内圈故障</td><td><span class="status-pass">1.0</span></td><td><span class="status-fail">0.0</span></td><td><span class="status-fail">0.0</span></td></tr>
  <tr><td>气穴溃灭</td><td><span class="status-fail">0.0</span></td><td><span class="status-fail">0.0</span></td><td><span class="status-fail">0.0</span></td></tr>
</table>

<div class="callout">
  <span class="hl">结论</span>：统计阈值比固定比值更保守。松靴（峭度特征突出）三种模式都能检出；其他故障在统计阈值下未触发，说明需要更多正常样本来稳定统计阈值。
</div>

<hr>

<!-- 第4节 -->
<h2 id="sec4">4. 故障诊断综合报告</h2>

<blockquote>
  <strong>目的</strong>：用真实数据展示完整的诊断流程和结果。<br>
  <strong>数据</strong>：7柱塞、1480 RPM、采样率 20kHz、三轴振动信号
</blockquote>

<div class="figure">
  <img src="{fig4}" alt="诊断综合报告">
  <div class="figure-caption">图4：柱塞泵故障诊断综合报告 — 时域波形 + FFT频谱（非均匀横轴）+ 包络谱 + 故障排序 + 诊断依据</div>
</div>

<h3>诊断结果</h3>

<table>
  <tr><th>故障类型</th><th>判定</th><th>置信度</th><th>主触发特征</th><th>比值</th></tr>
  <tr><td>松靴/滑靴脱落</td><td><span class="status-pass">触发</span></td><td>2.0</td><td>Z轴峭度 + X轴角域峭度</td><td>3.45x / 9.86x</td></tr>
  <tr><td>配流盘磨损</td><td><span class="status-pass">触发</span></td><td>2.0</td><td>0~100Hz频带能量 + 7阶次幅值</td><td>156x / 14x</td></tr>
  <tr><td>柱塞-缸孔磨损</td><td><span class="status-pass">触发</span></td><td>2.0</td><td>7阶次 + 14阶次幅值</td><td>14x / 6.4x</td></tr>
  <tr><td>斜盘磨损</td><td><span class="status-fail">未触发</span></td><td>0.0</td><td>—</td><td>—</td></tr>
  <tr><td>轴承外圈故障</td><td><span class="status-pass">触发</span></td><td>1.0</td><td>Z轴峭度</td><td>3.45x</td></tr>
  <tr><td>轴承内圈故障</td><td><span class="status-pass">触发</span></td><td>1.0</td><td>Z轴峭度</td><td>3.45x</td></tr>
  <tr><td>气穴溃灭</td><td><span class="status-fail">未触发</span></td><td>0.0</td><td>—</td><td>—</td></tr>
</table>

<div class="callout">
  <span class="hl">结论</span>：检测到多种可能故障，最可能是<strong>松靴/滑靴脱落</strong>。配流盘磨损和柱塞-缸孔磨损同时触发，可能与松靴共存（内泄漏+冲击）。
</div>

<hr>

<!-- 第5节 -->
<h2 id="sec5">5. 故障-信号映射表</h2>

<table>
  <tr><th>故障类型</th><th>类别</th><th>核心特征频率</th><th>搜寻区域</th><th>关键区分点</th></tr>
  <tr><td>松靴/滑靴</td><td>冲击</td><td>f<sub>p</sub>=172.67Hz</td><td>包络谱（高频共振带）</td><td>包络谱 f<sub>p</sub> 谐波，有周期性</td></tr>
  <tr><td>轴承外圈</td><td>冲击</td><td>BPFO&asymp;4~8&times;f<sub>r</sub></td><td>包络谱（高频共振带）</td><td>无转频边频</td></tr>
  <tr><td>轴承内圈</td><td>冲击</td><td>BPFI&asymp;5~9&times;f<sub>r</sub></td><td>包络谱（高频共振带）</td><td>有转频边频</td></tr>
  <tr><td>气穴溃灭</td><td>冲击(随机)</td><td>无离散频率</td><td>高频底噪</td><td>随机冲击，无周期性</td></tr>
  <tr><td>配流盘磨损</td><td>低频周期</td><td>f<sub>p</sub> 谐波</td><td>低频 FFT</td><td>谐波全面抬升</td></tr>
  <tr><td>柱塞磨损</td><td>低频周期</td><td>f<sub>p</sub> 谐波</td><td>低频 FFT</td><td>低阶谐波为主</td></tr>
  <tr><td>斜盘磨损</td><td>低频周期</td><td>f<sub>r</sub> 谐波</td><td>低频 FFT</td><td>转频谐波为主</td></tr>
</table>

<hr>

<div class="footer">
  柱塞泵故障诊断算法技术报告 v7.23 · order_tracking_v2 · 2026-07-24
</div>

</body>
</html>"""

    output_path = os.path.join(OUT, "算法技术报告.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ {output_path}")


if __name__ == "__main__":
    generate_html()
