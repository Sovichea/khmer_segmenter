# Design Philosophy: Why Dictionary-First?

This document provides an in-depth discussion of my design philosophy behind `KhmerSegmenter`, explaining why my dictionary-first approach is fundamentally superior to ML-based training on Zero-Width Space (ZWS) annotations, and how I've built this project to serve as foundational infrastructure for both research and practical applications.

## Table of Contents

- [Purpose & Design Philosophy](#purpose--design-philosophy)
- [Why Viterbi over Deep Learning?](#why-viterbi-over-deep-learning)
- [Bridging the Engineering Gap](#bridging-the-engineering-gap-beyond-computer-science)
- [Why Dictionary-First Beats ML Training on ZWS](#why-dictionary-first-beats-ml-training-on-zws)
- [A Complementary Tool for ML Research](#a-complementary-tool-for-ml-research)
- [Foundation for Spellcheck & Grammar Tools](#foundation-for-spellcheck--grammar-tools)

---

## Purpose & Design Philosophy

My primary goal is **dictionary-accurate segmentation**. Unlike modern Machine Learning (ML) models that prioritize predicting conversational "intent" or deep semantic context, I focus on strictly aligning text with curated, approved Khmer wording sources.

### Why Viterbi over Deep Learning?

In the current NLP landscape (2026), there is a significant trade-off between **Contextual Awareness** (Deep Learning) and **Deterministic Efficiency** (Algorithmic).

| Feature | KhmerSegmenter (Viterbi) | ML-Based (Transformers/BERT) |
| :--- | :--- | :--- |
| **Logic** | "Search": Find the mathematically best path through a curated dictionary. | "Patterns": Infer boundaries based on patterns seen in millions of articles. |
| **Transparency** | **White Box**: If a word splits incorrectly, you simply update the dictionary or frequency table. | **Black Box**: Errors require retraining with thousands of examples; shifts are often opaque. |
| **Hardware** | **Ultra-Light**: Runs on anything (Drones, Mobile, Arduinos, Low-power CPUs). | **Heavy**: Usually requires GPUs or high-end CPUs and massive RAM. |
| **Size** | **Tiny**: ~3 MB (Dictionary size) + < 100KB of logic. | **Massive**: 500 MB to 10 GB+ of model weights. |
| **Determinism** | **100% Consistent**: Same input + Same dict always equals Same output. | **Stochastic**: Can "hallucinate" or vary results based on subtle context shifts. |

### The "Context" Argument

Critics of Viterbi often point out its "Blindness" to semantic context (long-range dependencies). However, for technical documentation, standard literature, and dictionary-driven applications, I consider this "blindness" a **feature**:
*   It ensures that my segmenter never "imagines" words or slang not approved in your curated source.
*   It provides a high-performance baseline (95% accuracy for standard text) for a fraction of the computational cost.

### Bridging the Engineering Gap (Beyond Computer Science)

In many engineering fields—such as **Robotics, UAV/Drone systems, and Industrial Embedded Control**—there is effectively **zero support** for the Khmer language. While Computer Science has moved toward massive Machine Learning models, these "modern" solutions are impossible to run on the low-level microcontrollers and embedded processors that power real-world machinery.

This creates a digital divide: Khmer becomes a "computer-only" language, excluded from the hardware that engineers use every day.

I aim to break this barrier with `KhmerSegmenter`. By using the Viterbi algorithm—a purely mathematical and algorithmic approach—I provide a solution that can be implemented in **C, C++, or Rust** and run on devices with only a few megabytes (or even kilobytes) of memory. This project isn't just about NLP; it's about making Khmer a viable language for the next generation of physical engineering.

Ultimately, I've designed `KhmerSegmenter` for **portability and control**. It's the "Swiss Army Knife" of Khmer NLP—small, sharp, and reliable.

## Why Dictionary-First Beats ML Training on ZWS

Many ML-based Khmer segmentation implementations (CRF, HMM, LSTM, Transformers) rely on Zero-Width Space (ZWS) characters in training text to learn segmentation boundaries. While this approach may seem practical, it suffers from a **fundamental data quality problem** that undermines accuracy.

### The ZWS Inconsistency Problem

**The core issue:** There are no exact, universally agreed-upon rules for where to place ZWS in Khmer text. 100 different people will annotate the same text with ZWS in 100 different ways. This inconsistency means:

- Training data contains **conflicting signals** about correct segmentation
- Models learn to "average out" human inconsistency rather than linguistic correctness
- Accuracy is inherently limited by the noise in the training annotations
- Different annotators' preferences create unpredictable model behavior

### Why ML Researchers Still Use ZWS Despite This

**1. Data Availability & Scale**
- ZWS-marked text exists "in the wild" (web pages, documents, social media)
- Easy to collect millions of tokens without manual expert curation
- Even noisy annotations provide *some* statistical signal
- ML models can learn to average behaviors across many inconsistent annotators

**2. Handling Novel Words**
- Neural models can generalize to words never seen in training
- Real-world text constantly evolves: slang, technical terms, transliterations, code-switching
- Dictionary-only approaches struggle with neologisms and informal language

**3. Context Awareness**
- CRF/LSTM models learn contextual patterns beyond word boundaries
- Can handle ambiguous cases where segmentation depends on semantic meaning
- Example: compound words vs. separate words varying by context

**4. Academic Incentives**
- Research community favors novel ML techniques over data curation
- Building comprehensive dictionaries requires expensive linguistic expertise
- Papers on "new architectures" are more publishable than "better dictionaries"

### Why This Dictionary Approach Is Fundamentally Superior

**My implementation addresses the ZWS problem by ignoring it entirely:**

#### 1. **Precision Over Noise**
- Clean, curated dictionary data beats inconsistent human annotations
- **100% deterministic**: Same input always produces identical output
- No "averaging" of conflicting signals—just correct linguistic structure

#### 2. **Explainable & Debuggable**
- **White box system**: If a word splits incorrectly, update the dictionary or frequency table
- ML models require retraining with thousands of examples; errors are opaque
- Engineers can trace exactly why each segmentation decision was made

#### 3. **No Training Required**
- Works immediately without expensive annotation or GPU training time
- No model "drift" or degradation as language evolves
- Update dictionary → instant improvement

#### 4. **Computational Efficiency**
- Dictionary lookup + Viterbi is orders of magnitude faster than neural inference
- ~0.34ms per call (C port) vs. ~5-50ms for transformer models
- Runs on embedded systems, not just cloud GPUs

#### 5. **Portability**
- Pure algorithmic logic ports to any language (C, Rust, JavaScript, WASM)
- No dependency on heavy ML frameworks (PyTorch, TensorFlow)
- As demonstrated: works on drones, Arduino, embedded systems

### The Hybrid Insight: Statistical + Linguistic

My implementation isn't purely rule-based—it's a **prescriptive statistical model**:

- **Dictionary**: Provides linguistic authority (what words exist)
- **Frequency costs**: Enables probabilistic reasoning (which segmentation is more likely)
- **Viterbi algorithm**: Finds the globally optimal path through ambiguous cases

By combining curated knowledge with probabilistic search, I get the best of both worlds: **the precision of linguistic expertise with the flexibility of statistical methods.**

### When Dictionary-First Wins

This approach is particularly superior for:

✅ **Production systems** needing reliability and consistency  
✅ **Technical documentation** where standard vocabulary dominates  
✅ **Applications requiring explainability** (legal, medical, government)  
✅ **Resource-constrained environments** (mobile, embedded, edge computing)  
✅ **Cross-platform deployment** (Windows, Linux, WASM, bare metal)

**Coverage reality:** A well-curated dictionary covers 95%+ of standard text. For the remaining 5% (names, slang, neologisms), **unknown word handling** with frequency-based fallback is more transparent than ML "hallucinations."

### The Philosophical Difference

- **ML approach**: Optimize for "average human behavior" learned from noisy data
- **Dictionary approach**: Optimize for "correct linguistic structure" defined by experts

For applications where **consistency, accuracy, and control** matter more than flexibility with informal language, the dictionary-first approach is not just competitive—it's fundamentally more sound.

---

## A Complementary Tool for ML Research

**My project does not compete with current ML research—it aims to enhance it.**

While the discussion above critiques ZWS-based training data, my goal is not to dismiss machine learning approaches but to provide a **better foundation** for them. Here's how:

### Improving Training Data Quality

Researchers and ML practitioners can use `KhmerSegmenter` as a **preprocessing tool** to clean and segment web-scraped or noisy Khmer text:

1. **Segment dictionary-accurate words** using this tool to establish a high-quality baseline
2. **Identify unknown words** that the dictionary doesn't cover (names, slang, technical terms, neologisms)
3. **Apply ML/neural approaches** specifically to the unknown word problem where they excel
4. **Generate clean training datasets** by combining dictionary-accurate segmentation with human-validated handling of unknowns

### Benefits for Khmer LLM Development

This hybrid pipeline significantly improves training accuracy for Large Language Models in Khmer:

- **Reduces noise:** Eliminates inconsistent ZWS annotations from web text
- **Provides consistency:** 95%+ of tokens segmented deterministically and correctly
- **Focuses human effort:** Annotators only need to handle genuinely ambiguous cases
- **Scales efficiently:** Process millions of web pages with consistent, fast segmentation
- **Enables bootstrapping:** Use dictionary-accurate segmentation to generate initial datasets, then fine-tune with ML

### Use Case: Khmer LLM Pre-training Pipeline

```
Web Text (noisy ZWS) 
    → KhmerSegmenter (dictionary baseline)
    → Unknown word detection
    → ML-based context analysis (for unknowns only)
    → Human validation (targeted on ambiguous cases)
    → High-quality training corpus
    → Better Khmer LLM
```

**The key insight:** By providing a deterministic, linguistically-grounded baseline for known vocabulary, this tool allows ML researchers to focus their models on the genuinely hard problems (context, ambiguity, novel words) rather than re-learning basic dictionary knowledge from noisy annotations.

This is a **collaborative approach**: combine the strengths of curated linguistic knowledge (dictionary) with the strengths of statistical learning (handling unknowns and context), rather than forcing one method to solve all problems.

---

## Foundation for Spellcheck & Grammar Tools

Beyond research applications, I've built `KhmerSegmenter` to provide **essential infrastructure** for developers building practical language tools across diverse platforms.

### Why Word Segmentation Is Critical for Khmer NLP Tools

Unlike space-delimited languages (English, French, etc.), Khmer requires **accurate word boundary detection** before any higher-level language analysis can occur. Without proper segmentation:

- Spellcheckers cannot identify which character sequences constitute "words" to validate
- Grammar checkers cannot parse sentence structure or identify syntactic errors
- Auto-complete and predictive text cannot suggest valid word completions
- Text-to-speech engines cannot determine proper pronunciation boundaries

### Applications Enabled by This Project

Developers can use `KhmerSegmenter` as a **core dependency** to build:

**Text Editors & IDEs**
- Real-time spellcheck highlighting (VS Code, Sublime Text, Notepad++, Vim)
- Grammar suggestions and error detection
- Auto-complete and word suggestion engines
- Find/replace with word-boundary awareness

**Office & Productivity Software**
- Word processors (Microsoft Word, Google Docs, LibreOffice plugins)
- Note-taking apps (Notion, Evernote, Obsidian)
- Email clients with Khmer composition support
- PDF annotation tools with proper word selection

**Web & Mobile Platforms**
- Browser extensions for spellcheck (Chrome, Firefox, Edge)
- Mobile keyboard apps with predictive text (Android, iOS)
- Web-based text editors (TinyMCE, CKEditor, ProseMirror)
- Content Management Systems (WordPress, Drupal) plugins

**Developer Tools & APIs**
- Language server protocols (LSP) for Khmer
- RESTful APIs for text validation services
- Batch document processing pipelines

### Technical Advantages for Tool Developers

✅ **Multi-language support**: C, Python, Rust, WASM ports enable integration anywhere  
✅ **Lightweight**: ~3MB dictionary + minimal runtime overhead  
✅ **Fast**: Real-time performance for interactive applications (<1ms per typical sentence)  
✅ **Deterministic**: Consistent results enable reliable testing and user experience  
✅ **Offline-capable**: No API calls or internet dependency required  
✅ **Cross-platform**: Works identically on Windows, macOS, Linux, mobile, and web

### Example Integration: Browser Spellcheck Extension

```javascript
import init, { WasmKhmerSegmenter } from "./wasm/khmer_segmenter.js";

await init();
const dictionaryBytes = new Uint8Array(
  await (await fetch("./data/khmer_dictionary.kdict")).arrayBuffer(),
);
const segmenter = new WasmKhmerSegmenter(dictionaryBytes);

const result = segmenter.analyze("សម្បត្ត", true);
console.log(result.segments);
console.log(result.diagnostics);
```

The browser build accepts compiled KDIC bytes directly. Pass `true` as the
second argument to enable the higher-recall experimental typo-span analysis.

By providing **reliable word segmentation** as a solved problem, I allow developers to focus on the unique challenges of their specific applications (UI/UX, context-aware suggestions, language-specific grammar rules) rather than re-implementing basic tokenization.

---

## Summary

The dictionary-first approach is not just an alternative to ML-based segmentation—it's a **fundamentally better foundation** for building robust Khmer language tools. By providing:

1. **Clean, deterministic segmentation** free from ZWS annotation noise
2. **Infrastructure for ML research** to improve training data quality
3. **Foundation for practical tools** like spellcheckers and grammar checkers

`KhmerSegmenter` enables the entire Khmer NLP ecosystem to build on solid, reliable, and portable linguistic infrastructure.
