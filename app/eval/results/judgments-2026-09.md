# Incomplete-judgments pass — 2026-09-11

**Who judged:** Claude (Fable 5.1), in a Claude Code session. Not the original human labeler.
**What was judged:** every chunk that landed in any strategy's top-10 (dense, bm25, rrf, hybrid;
k=10) for one of the 15 golden queries and carried no label — 237 candidates in total, produced by
`uv run python -m app.eval.ablation --unjudged` at commit `6d1bee8`.
**Rule:** add a chunk only if it directly answers the query *as written*. Same topic is not enough.
Heading-only fragments (a risk-factor title with the body in the next chunk) were excluded even
when the title matched, because the body chunk carries the answer. Chunks whose only match was in
the 150-char overlap tail were excluded.
**Outcome:** 74 chunks added across 14 queries; 1 query unchanged. Gold set grows from 54 to
128 labels. Every addition is listed below with the decisive phrase so a reviewer can disagree
with a specific call rather than the whole pass.

Why this matters: the original labels were made from an 8–9 chunk shortlist per query. Against a
~130-chunk pool the retriever surfaces genuinely relevant passages the labeler never saw, and the
metrics would score those as misses. This pass removes that bias. It is an LLM-judge step and is
labeled as such in `app/eval/golden.py` and the README.

---

## Case 0 · AAPL · single-source suppliers / manufacturing concentration with outsourcing partners
Labeled before: 23, 24, 27. Added: **9, 15, 96**.
- 9 — "A significant majority of the Company's manufacturing is performed in whole or in part by outsourcing partners located primarily in China mainland, India, Japan, South Korea, Taiwan and Vietnam."
- 15 — "Because the Company relies on single or limited sources for the supply and manufacture of many critical components, a business interruption affecting such sources would exacerbate any negative consequences."
- 96 — MD&A: "The Company utilizes several outsourcing partners to manufacture subassemblies … and to perform final assembly and testing of finished products … manufacturing purchase obligations of $56.2 billion."
- Excluded 28: overlap tail plus a new heading about defects; the substance is in labeled 27.

## Case 1 · AAPL · net sales / gross margins vs FX and macro pressures
Labeled before: 74, 75, 76, 77. Added: **86, 87, 88, 89, 91, 92**.
- 86 — "Macroeconomic conditions, including inflation, interest rates and currency fluctuations, have directly and indirectly impacted … the Company's results of operations."
- 87 — Tariffs: "can have a material adverse impact on … pricing and gross margin."
- 88 — "Trade and other international disputes can have an adverse impact on the overall macroeconomic environment and result in shifts and reductions in consumer spending."
- 89 — "The weakness in foreign currencies relative to the U.S. dollar had an unfavorable year-over-year impact on Americas net sales."
- 91 — "Products gross margin percentage decreased … primarily due to a different mix of products and tariff costs."
- 92 — "The Company's future gross margins can be impacted by a variety of factors … gross margins will be subject to volatility and downward pressure."
- Excluded 73: heading only. Excluded 90, 93: product-category and opex tables, no FX or macro content.

## Case 2 · AAPL · antitrust / App Store / DMA regulatory actions
Labeled before: 64, 65, 66, 67. Added: **none**.
- 58 lists "antitrust" inside a 30-item catalogue of law areas; it discloses no action. 63 is the section heading. 69 is the tail of the risk factor ("the outcomes of such investigations") without naming any action. All excluded.

## Case 3 · META · Reality Labs risks and VR/AR investments
Labeled before: 472, 473, 647, 659. Added: **458, 474, 484, 504, 693**.
- 458 — "we have relatively limited experience with consumer hardware products and virtual and augmented reality technology, which may adversely affect our ability to successfully develop and market these."
- 474 — "our Reality Labs strategy and investments may not be successful in the foreseeable future, or at all" plus the regulatory areas (medical devices, tariffs, export controls) that "may delay or impede the development of our products."
- 484 — competition in "augmented and virtual reality products and services … efforts to develop the metaverse."
- 504 — "our investments in Reality Labs reduced our 2025 overall operating profit by approximately $19.19 billion, and we expect our 2026 Reality Labs operating losses to remain similar."
- 693 — "RL loss from operations in 2025 increased $1.46 billion, or 8% … estimated losses on non-cancelable purchase commitments for RL inventory."
- Excluded 471: heading only. Excluded 680, 687: RL revenue definition and +3% revenue line, not risks or investment.

## Case 4 · META · AI infrastructure investment, capex, data-center costs
Labeled before: 504, 648, 690. Added: **460, 647, 658, 681, 691, 703, 707, 708**.
- 460 — "we expect our AI initiatives will require increased investment in infrastructure and headcount." (qualitative, same standard as labeled 504)
- 647 — "Capital expenditures, including principal payments on finance leases, were $72.22 billion for the year ended December 31, 2025."
- 658 — "Our FoA investments include expenses relating to headcount, data centers, and technical infrastructure … we expect our AI initiatives will require significantly increased investment in infrastructure."
- 681 — cost of revenue "mainly include[s] expenses related to the operation of our data centers and technical infrastructure, such as depreciation expense from servers, network infrastructure and buildings."
- 691 — R&D "increase was mostly due to higher employee compensation and infrastructure costs related to research and development, including our AI initiatives."
- 703 — "$69.69 billion of purchases of property and equipment as we continued to invest in servers, data centers, and network infrastructure … capital expenditures of approximately $115 billion to $135 billion in 2026 to support our AI efforts."
- 707 — "We have increased investments in infrastructure and AI initiatives and expect to continue to do so." (qualitative)
- 708 — leases "not yet commenced, with total lease obligations of approximately $103.77 billion, mostly for data centers" and "$131.05 billion of contractual commitments … servers and network infrastructure, data centers."
- Excluded 659 (Reality Labs), 709 (debt and buybacks), 705 (FCF definition).

## Case 5 · META · GDPR / DMA and privacy regulation as European risks
Labeled before: 432, 433, 450, 452. Added: **426, 448, 572, 573, 576, 577, 590, 595, 597, 599, 617, 650**.
- 426 — risk summary bullet naming "General Data Protection Regulation (GDPR), Digital Markets Act (DMA), Digital Services Act (DSA), UK Online Safety Act (OSA), Artificial Intelligence Act (EU AI Act)."
- 448 — "the GDPR, ePrivacy Directive, DMA, and U.S. state privacy laws, have impacted … our ability to use such signals … users opting to control certain types of ad targeting in Europe."
- 572 — CJEU / Privacy Shield / SCCs; "the IDPC issued an administrative fine of EUR €1.2 billion."
- 573 — "bring its processing operations into compliance with Chapter V GDPR"; EU-U.S. Data Privacy Framework.
- 576 — "product changes and controls as a result of requirements under the European General Data Protection Regulation (GDPR) … significant penalties for non-compliance."
- 577 — "the interpretation and enforcement of the GDPR, as well as the imposition and amount of penalties for non-compliance, are subject to significant uncertainty."
- 590 — notifications to "the IDPC, our lead European Union privacy regulator under the GDPR"; UK GDPR; European Commission DSA investigations.
- 595 — "Compliance with … the GDPR, … the ePrivacy Directive, the DMA, the DSA, the OSA … require significant operational resources."
- 597 — "we are subject to restrictions and requirements under the DMA, including in areas such as the combination of data across services and product design."
- 599 — failure to comply with "GDPR and UK GDPR, … ePrivacy Directive, DMA, DSA … may result in significant monetary fines."
- 617 — "laws and regulations … relating to cybersecurity and data protection, including the GDPR and EU member state laws implementing the EU Cybersecurity Directive (NIS2)."
- 650 — MD&A: "General Data Protection Regulation … ePrivacy Directive, European Digital Services Act, Digital Markets Act … have impacted our ability to use data signals … change the legal basis for behavioral advertising … in the European Union."
- Excluded 568 (generic heading), 575 (substance is India/WhatsApp), 606 (Copyright Directive and DSA content rules, not privacy), 608 (payments law).
- Note: this query's gold set grows from 4 to 16. Meta's 10-K spends several pages on exactly this; the original shortlist could not have covered it.

## Case 6 · MSFT · cybersecurity threats and breaches, nation-state attacks
Labeled before: 123, 124, 125, 126. Added: **127, 128, 129, 130, 131, 133, 137**.
- 127 — "Malicious actors may employ the supply chain to introduce malware … threat actors may gain undetected access to other networks and systems."
- 128 — "Breaches of our facilities, network, or data security can disrupt … subject us to ransomware attacks."
- 129 — "Increasing use of generative AI models in our internal systems may create new attack surfaces or methods for adversaries."
- 130 — "Threats to or attacks on our own infrastructure, such as the nation-state attack described in the prior risk factor, have also affected our customers … exploiting previously unknown ('zero-day') vulnerabilities."
- 131 — "Adversaries that acquire user account information can use that information to compromise our users' accounts … Open source software can also contain vulnerabilities."
- 133 — "Cyberattacks could adversely impact our customers even if our production services are not directly compromised … Exchange Server."
- 137 — "The continued occurrence of high-profile data breaches … we may fail to identify or mitigate insider threat activities."
- Excluded 122 (heading only), 132 (customer support constraints, not a threat disclosure), 134 (defensive measures, not threats), 161 (cybersecurity regulation).

## Case 7 · MSFT · risks of developing and deploying AI
Labeled before: 143, 145, 146. Added: **112, 117, 160**.
- 112 — "We will bear significant development and operational costs to build and support the AI models, services, platforms, and infrastructure … responsive to … new and potential regulatory developments, and public scrutiny."
- 117 — "Our AI systems … may be used in ways that are unintended or inappropriate … fraudulent or abusive activities through our cloud-based and AI services."
- 160 — "shifting AI export controls policies, like the AI Diffusion Rule … potential AI-related rulemakings could adversely affect Microsoft's business." (borderline: regulatory risk specific to AI)
- Excluded 118 (generic new-product investment risk with AI as one list item), 144 (heading only), 189 (OpenAI partnership description, not a risk).

## Case 8 · MSFT · datacenter capacity, infrastructure, component supply
Labeled before: 148, 150, 201. Added: **149, 191, 226**.
- 149 — "insufficient or unavailable power or water supply, or inadequate storage and compute capacity could diminish the quality of our products."
- 191 — "expand our datacenter locations and increase our server capacity … Our datacenters depend on the availability of permitted and buildable land, predictable energy, networking supplies, and servers, including graphics processing units ('GPUs')."
- 226 — "Additions to property and equipment will continue, including new facilities, datacenters … capital expenditures to support growth in our cloud offerings and our investments in AI infrastructure."
- Excluded 204, 205 (margin impact of scaling AI infrastructure, not capacity or supply), 189 (OpenAI capacity rights).

## Case 9 · NVDA · U.S. export controls and licensing on sales to China
Labeled before: 333, 334, 335, 336. Added: **328, 329, 331, 332, 337, 338, 339, 340, 341, 342, 344, 345, 346, 382**.
- 328 — "The United States has imposed unilateral worldwide controls restricting GPUs and associated products, and it is likely that additional unilateral or multilateral controls will be adopted."
- 329 — controls "subject downstream users of our products to restrictions on the use, resale, repair, or transfer … even outside China."
- 331 — "Reduced demand due to export controls has and could in the future lead to excess inventory"; China regulators' inquiry.
- 332 — "compliance with applicable U.S. export controls, which required us to offer degraded products to the Chinese market … a series of shifting and expanding export control restrictions."
- 337 — "The export controls applicable to China are complex … we were effectively foreclosed from competing in China's data center computing/compute market."
- 338 — "the USG has also imposed worldwide export controls … The IFR would have imposed a worldwide licensing requirement on our data center products, such as our H200, GB200 and GB300."
- 339 — rescission of the AI Diffusion IFR; "The replacement rule may impose new restrictions … and/or add license requirements"; GAIN AI Act.
- 340 — "if the USG does not grant licenses in a timely manner or denies licenses to significant customers … the licenses have already and may in the future be temporary, impose burdensome conditions."
- 341 — "the USG has changed and may again change the export control rules at any time and further subject a wider range of our products to export restrictions and licensing requirements."
- 342 — "the USG already imposed license conditions … may impose additional conditions such as requiring chip tracking and throttling mechanisms."
- 344 — export controls on gaming products, Hong Kong warehousing, and "may also impose export controls on our networking products."
- 345 — "Export controls have and are likely in the future to have a disproportionate impact on NVIDIA … 'design-out' certain U.S. semiconductors."
- 346 — "export controls have in the past and may in the future negatively impact demand for our products … not only in China … as we recently experienced with the H20."
- 382 — MD&A: "$60 million in H20 revenue under those licenses. In February 2026, the USG granted a license that would allow us to ship small amounts of H200 products to specific China-based customers."
- Excluded 348 (import restrictions and open-source models, not export controls), 349 (Chinese-government restrictions, not U.S. controls).
- Note: gold set grows from 4 to 18. The export-control risk factor runs several pages and every chunk of it answers the query.

## Case 10 · NVDA · third-party foundries and manufacturing capacity
Labeled before: 252, 253, 254, 269. Added: **268, 293**.
- 268 — "We depend on foundries to manufacture our semiconductor wafers … lack of guaranteed supply of components and capacity … failure by our foundries or contract manufacturers to … provide adequate levels of manufacturing or test capacity."
- 293 — "China, Hong Kong, Israel, Korea and Taiwan where the manufacture of our product components and final assembly of our products are concentrated … The ultimate impact on us, our third-party foundries and other suppliers of being located and consolidated in certain geographical areas is unknown."
- Excluded 241 (risk-factor summary bullet), 267 (heading only, body is 268), 258 (customers' datacenter buildout), 272 (defects), 386 (macro).

## Case 11 · NVDA · customer concentration
Labeled before: 307, 308, 402. Added: **309**.
- 309 — "We generate a significant amount of our revenue from a limited number of indirect customers, and we estimate some individually representing 10% or more of our revenue … The loss of any of our large customers."
- Excluded 401: ends on the heading "Concentration of Revenue"; the body is labeled 402.

## Case 12 · TSLA · dependence on Elon Musk and key personnel
Labeled before: 754, 757, 809. Added: **755, 756, 807, 808**.
- 755 — "Employees may leave Tesla or choose other employers over Tesla … strong competition for individuals with skillsets needed for our business."
- 756 — "If we are unable to obtain the requisite shareholder approvals … our ability to retain and hire qualified personnel may be harmed."
- 807 — "The product goals were designed to incentivize Elon Musk to devote time and energy to development of these products … no assurance that these investments will deliver the expected … benefits."
- 808 — "If Elon Musk were forced to sell shares of our common stock … such sales could cause our stock price to decline."
- Excluded 753 (heading only), 748 (public credibility; management-team speculation is incidental), 765 (unions).

## Case 13 · TSLA · ramping production at new factories
Labeled before: 714, 715, 716, 721. Added: **713, 722, 738, 818**.
- 713 — "We may experience issues or delays in developing, launching and ramping the production of our products … We also have previously experienced and may in the future experience launch and production ramp delays."
- 722 — "If we experience any issues or delays in meeting our projected timelines, costs, capital efficiency and production capacity for our new factories."
- 738 — "issues with lithium-ion cells or other components manufactured at our Gigafactories, which may harm the production … If we are unable to or otherwise do not maintain and grow our respective operations." (borderline: factory production risk, not a new-factory ramp)
- 818 — MD&A: "These plans are subject to uncertainties inherent in establishing and ramping manufacturing operations … affecting not only vehicle production, but also facility expansions."
- Excluded 718 (component supply), 729 (fragment), 817 (production plans, not risks), 827 (capex projection), 805 (guidance accuracy).

## Case 14 · TSLA · automotive competition and autonomous-driving adoption
Labeled before: 731, 732, 735, 736. Added: **733, 734**.
- 733 — "The target demographics for our vehicles are highly competitive. Sales of vehicles in the automotive industry tend to be cyclical."
- 734 — "our success will be dependent upon … the acceptance and adoption by consumers of autonomous driving solutions, and Robotaxi as a preferable option, amid growing competition. If the uptake rate for autonomous driving solutions does not develop as we expect."
- Excluded 714 (development and ramp of autonomy, not adoption), 790 (regulation of autonomy), 819 and 822 (MD&A strategy; competition mentioned only in passing), 748 (credibility).
