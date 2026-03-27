# Language Support Guide

**Complete guide to 50+ supported languages with regional variants**

---

## Overview

Deepgram Nova-3 represents a fundamental shift in global speech recognition. Rather than forcing all languages through an English-optimized model, Nova-3 adapts to the linguistic structure of each language—from tonal Vietnamese to agglutinative Hungarian, from syllable-timed Japanese to stress-timed English.

**Key Capabilities:**
- **40+ individual languages** with regional dialect support
- **Universal keyterm prompting** across all languages (500 tokens)
- **Multilingual model** processing 10 languages simultaneously
- **Automatic language detection** for 35 languages (batch mode)
- **Regional variants** for optimal local accuracy

---

## Complete Language Matrix

### Western Europe

#### English (5 Regional Variants)
- **en-US**: American English (General American accent)
- **en-GB**: British English (Received Pronunciation & regional UK accents)
- **en-AU**: Australian English (Australian accent patterns)
- **en-IN**: Indian English (South Asian English varieties)
- **en-NZ**: New Zealand English (Kiwi accent)
- **en**: Generic English (auto-selects based on audio)

**Use Cases**: International content, regional media, multilingual families

#### Spanish (2 Regional Variants)
- **es**: European Spanish (Castilian, Andalusian dialects)
- **es-419**: Latin American Spanish (Mexican, Argentine, Colombian, etc.)

**Key Differences**: Pronunciation (z/c sounds), vocabulary (coche vs carro), voseo usage

#### French (2 Regional Variants)
- **fr**: European French (Metropolitan French)
- **fr-CA**: Canadian French (Québécois, Acadian)

**Key Differences**: Pronunciation patterns, vocabulary, anglicisms in Canadian French

#### Portuguese (2 Regional Variants)
- **pt-PT**: European Portuguese (Continental)
- **pt-BR**: Brazilian Portuguese (most widely spoken variant)

**Key Differences**: Pronunciation, gerund usage, vocabulary differences

#### German (2 Regional Variants)
- **de**: Standard German (Hochdeutsch)
- **de-CH**: Swiss German (Schweizerdeutsch influences)

**Key Differences**: Swiss vocabulary, pronunciation patterns

#### Dutch (2 Regional Variants)
- **nl**: Netherlands Dutch
- **nl-BE**: Belgian Dutch (Flemish)

**Key Differences**: Pronunciation, vocabulary, tone patterns

#### Other Western European Languages
- **it**: Italian
- **ca**: Catalan (distinct from Spanish)

---

### Eastern & Southern Europe

#### Slavic Languages
- **ru**: Russian - Rich inflection system, palatalization, Cyrillic script
- **uk**: Ukrainian - Palatalized consonants, open vowels, Cyrillic script
- **pl**: Polish - Seven grammatical cases, nasal vowels, consonant clusters
- **cs**: Czech - Free word order, complex consonant clusters
- **bg**: Bulgarian - Fast vowel reductions, definite articles, Cyrillic script
- **sk**: Slovak - Similar to Czech but distinct phonology

**Challenges Solved**: Case endings, consonant clusters, homophone resolution

#### Uralic Languages
- **hu**: Hungarian - Agglutinative (long compound suffix chains), vowel harmony
- **fi**: Finnish - Agglutinative structure, vowel harmony, long compound words

**Challenges Solved**: Morpheme segmentation, compound word boundaries

#### Other Southern European Languages
- **ro**: Romanian - Romance language with Slavic influences
- **el**: Greek - Unique script, grammatical complexity
- **tr**: Turkish - Agglutinative, vowel harmony, rapid morphological changes

---

### Nordic & Baltic Languages

#### Nordic Languages
- **sv**: Swedish (generic)
- **sv-SE**: Swedish (Sweden-specific dialect optimization)
- **no**: Norwegian (Bokmål and Nynorsk varieties)
- **da**: Danish (generic)
- **da-DK**: Danish (Denmark-specific optimization)
- **fi**: Finnish (see Uralic section above)

**Characteristics**: Tonal accents (Swedish/Norwegian), stød (Danish), vowel length distinctions

#### Baltic Languages
- **lt**: Lithuanian - Complex case system, pitch accent, Baltic branch
- **lv**: Latvian - Pitch accent, three-way vowel length distinction
- **et**: Estonian - Finno-Ugric family, vowel harmony, agglutinative

**Challenges Solved**: Pitch accent recognition, vowel length, case ending accuracy

---

### Asian Languages

#### East Asia
- **ja**: Japanese
  - Mixed scripts: Hiragana, Katakana, Kanji
  - Syllable-timed rhythm (mora-based)
  - Loanword pronunciation (gairaigo)
  - Particle system

- **ko** / **ko-KR**: Korean
  - Hangul syllable blocks
  - Rapid conjugation patterns
  - Spacing ambiguity in compound words
  - Honorific levels

**Challenges Solved**: Script handling, syllable timing, loanword recognition, compound noun spacing

#### South Asia
- **hi**: Hindi
  - Devanagari script
  - Inflection-heavy verbs
  - Frequent English code-switching (Hinglish)
  - SOV word order

**Challenges Solved**: Hinglish recognition, inflection handling, code-switching boundaries

#### Southeast Asia
- **vi**: Vietnamese
  - **Fully tonal** (6 tones: level, rising, falling, question, tumbling, heavy)
  - Diacritical marks for tones
  - Syllable-based morphology
  - Regional variation (Northern, Central, Southern)

- **id**: Indonesian
  - Latin script, agglutinative affixation
  - No tones, consistent pronunciation

- **ms**: Malay
  - Similar to Indonesian but distinct vocabulary and pronunciation

**Challenges Solved**: Tone resolution, diacritic accuracy, regional accent handling

---

## Multilingual Model (`multi`)

**Special language code**: `multi`

**Processes 10 Languages Simultaneously:**
1. English
2. Spanish
3. French
4. German
5. Hindi
6. Russian
7. Portuguese
8. Japanese
9. Italian
10. Dutch

**Ideal For:**
- Mixed-language content (Hinglish, Spanglish, Konglish)
- Multilingual families and international media
- Content with frequent code-switching
- International conferences or multilingual podcasts

**Usage**: Set `LANGUAGE=multi` in your environment or API request

---

## Universal Keyterm Prompting

**Available for ALL 40+ Languages**

### What Are Keyterms?

Keyterms are domain-specific vocabulary hints you provide to the model to improve accuracy for:
- Character names
- Location names
- Show-specific terminology
- Technical jargon
- Brand names
- Proper nouns

### Technical Specifications
- **Token Limit**: 500 tokens per request (~100 words or 20-50 optimized terms)
- **Format**: Comma-separated terms or newline-separated list
- **Availability**: ALL Nova-3 languages including `multi` model
- **No Training Required**: Works immediately without model retraining

### Language-Specific Use Cases

#### Korean (ko, ko-KR)
- Compound nouns with dynamic spacing
- Korean names (family name + given name)
- Konglish terms (English loanwords with Korean pronunciation)

#### Japanese (ja)
- Loanwords (gairaigo) with unique pronunciation
- Character names (family name + given name)
- Place names (地名)

#### Hindi (hi)
- Hindi-English mixed terms (Hinglish)
- Indian names and places
- Technical vocabulary

#### Polish & Russian (pl, ru)
- Names with various case endings
- Location names
- Technical terminology with Slavic inflections

#### Vietnamese (vi)
- Business terms without diacritics in spoken audio
- Names and places
- French loanwords

#### Greek (el)
- Greek names and locations
- Technical terminology in Greek alphabet
- English loanwords with Greek pronunciation

### Implementation

**CLI Tool** (manual keyterms):
```
/media/tv/Breaking Bad/Transcripts/Keyterms/Breaking Bad_keyterms.csv
```

**Format** (one term per line):
```
Walter White
Jesse Pinkman
Heisenberg
Los Pollos Hermanos
methylamine
```

**Web UI** (AI-powered generation):
- Navigate to video → Advanced Options → Generate Keyterms with AI
- Supports Anthropic Claude, OpenAI GPT, and Google Gemini
- Cost: ~$0.002-0.08 per generation (Gemini free tier available)

---

## Automatic Language Detection

**35 Languages Supported** (Batch Mode Only)

### How It Works
1. Send audio to Deepgram with `detect_language=true` parameter
2. Model analyzes audio and returns:
   - `detected_language`: Language code (e.g., "en", "es", "ja")
   - `language_confidence`: Score from 0-1 (higher = more confident)
3. Before transcription starts, Subgeneratorr treats any existing same-stem language-tagged sidecar (for example `Episode.spa.srt`) as already satisfying subtitle output for auto-detect runs.
4. If a new transcription is needed, Subgeneratorr writes the subtitle using the matching language tag when that code can be mapped safely (for example `.spa.srt`). If the request is `multi` or the detected language is unavailable or ambiguous for filename tagging, it falls back to `.und.srt`.

### Supported Languages (35 Total)
All major Nova-3 languages except some regional variants:
- Western Europe: en, es, fr, de, it, pt, nl, ca
- Eastern Europe: ru, uk, pl, cs, bg, hu, ro, sk
- Nordic/Baltic: sv, no, da, fi, lt, lv, et
- Southern Europe: el, tr
- Asia: ja, ko, hi, vi, id, ms

### Limitations
- **Batch mode only** - Not available for streaming/real-time transcription
- **No regional variant detection** - Returns base code (e.g., "en" not "en-AU")
- **Confidence threshold** - Low confidence may indicate mixed-language content

### When to Use
- **Unknown content**: Archival footage, found media, international downloads
- **Multilingual libraries**: Auto-classify content by language
- **Quality control**: Verify language tags on media files

### Configuration

**CLI Tool**:
```bash
DETECT_LANGUAGE=1  # Enable auto-detection (overrides LANGUAGE setting)
```

**API**:
```bash
curl --request POST \
  --header "Authorization: Token YOUR_DEEPGRAM_API_KEY" \
  --header "Content-Type: audio/wav" \
  --data-binary @youraudio.wav \
  "https://api.deepgram.com/v1/listen?model=nova-3&detect_language=true"
```

---

## Regional Variant Selection Guide

### When to Use Regional Variants

**English Variants**:
- **en-US**: American shows, Hollywood films
- **en-GB**: British TV (BBC, ITV), UK films
- **en-AU**: Australian content (ABC, SBS)
- **en-IN**: Bollywood English, Indian news
- **en-NZ**: New Zealand media

**Spanish Variants**:
- **es**: Spanish films, European Spanish content
- **es-419**: Mexican TV, Argentine films, Latin American content

**French Variants**:
- **fr**: French cinema, European French media
- **fr-CA**: Québécois films, Canadian French TV

**Portuguese Variants**:
- **pt-BR**: Brazilian telenovelas, Brazilian films (most content)
- **pt-PT**: Portuguese cinema, European Portuguese media

**German Variants**:
- **de**: German films, Austrian content
- **de-CH**: Swiss content with Swiss German influences

**Dutch Variants**:
- **nl**: Netherlands media
- **nl-BE**: Belgian content, Flemish TV

### Impact on Accuracy
Regional variants are trained on local accents, vocabulary, and pronunciation patterns:
- **Pronunciation**: "can't" in US vs UK, "about" in Canada vs US
- **Vocabulary**: "lorry" (UK) vs "truck" (US), "coche" (Spain) vs "carro" (Mexico)
- **Idioms**: Regional expressions unique to dialect

**Accuracy Gain**: 10-20% WER improvement for region-specific content vs generic model

---

## Implementation Examples

### Example 1: Single Language (Korean Drama)

```bash
# CLI Tool
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/media/tv/KoreanDrama \
  -e LANGUAGE=ko \
  cli
```

**Keyterms** (`/media/tv/KoreanDrama/Transcripts/Keyterms/KoreanDrama_keyterms.csv`):
```
박민영
서울
강남
청담동
```

### Example 2: Regional Variant (British TV)

```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/media/tv/Doctor\ Who \
  -e LANGUAGE=en-GB \
  cli
```

### Example 3: Multilingual Content

```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/media/movies/Multilingual \
  -e LANGUAGE=multi \
  cli
```

**Best For**: Spanish-English code-switching, Hinglish content, European multilingual films

### Example 4: Auto-Detection for Unknown Content

```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/media/archive/unknown \
  -e DETECT_LANGUAGE=1 \
  cli
```

**Result**: Each file transcribed in its detected language, logged to deepgram-logs/
Subtitles are written with the detected language tag when possible; otherwise they use `.und.srt`.

### Example 5: Latin American Spanish Content

```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/media/tv/LatAm \
  -e LANGUAGE=es-419 \
  cli
```

---

## Performance Benchmarks

### Word Error Rate (WER) Improvements

Nova-3 delivers measurable accuracy improvements over Nova-2 across all languages:

**Highest Improvements** (Streaming Mode):
- Korean (ko): **27% WER reduction**
- Czech (cs): **24% WER reduction**
- Hindi (hi): **23% WER reduction**
- Polish (pl): **21% WER reduction**
- Japanese (ja): **19% WER reduction**

**Consistent Gains Across All Languages**:
- Every language improved over Nova-2 in both batch and streaming
- Streaming models show stronger relative improvements (best for real-time)
- Languages with higher baseline complexity (non-Latin scripts, tonal, agglutinative) see largest gains

### Keyterm Impact
- **Up to 90% accuracy improvement** for prompted terms
- **Character names**: Generic "speaker 0" → accurate "Walter White"
- **Technical terms**: Misrecognized jargon → correct terminology
- **Location names**: Generic approximation → exact place name

---

## Best Practices for International Media Libraries

### 1. Organize by Language
```
/media/
  /english/
  /spanish/
  /japanese/
  /multilingual/
```

### 2. Use Regional Variants for Large Collections
- British TV → en-GB
- Latin American content → es-419
- Brazilian content → pt-BR

### 3. Create Language-Specific Keyterms
Store keyterms at show level for reuse across seasons:
```
/media/tv/ShowName/Transcripts/Keyterms/ShowName_keyterms.csv
```

### 4. Leverage Auto-Detection for Archives
Unknown or mixed-language archives benefit from automatic detection.

### 5. Use Multilingual Model for Code-Switching
Content with frequent language mixing (Hinglish, Spanglish) → `LANGUAGE=multi`

### 6. Monitor Logs for Language Confidence
Check `detected_language` and `language_confidence` in logs to identify potential issues.

---

## Troubleshooting

### Issue: Poor Accuracy Despite Correct Language
**Solution**: Use regional variant instead of generic code (e.g., en-GB vs en)

### Issue: Mixed-Language Content Misrecognized
**Solution**: Switch to `LANGUAGE=multi` for 10-language simultaneous processing

### Issue: Character Names Still Wrong
**Solution**: Add keyterms CSV with character names (500 token limit)

### Issue: Auto-Detection Choosing Wrong Language
**Solution**:
1. Check `language_confidence` score (low = ambiguous audio)
2. Manually specify language if confidence consistently low
3. Consider `multi` model if content has frequent code-switching

### Issue: Regional Variant Not Improving Accuracy
**Solution**: Verify you're using correct variant for content origin (e.g., pt-BR for Brazilian not pt-PT)

---

## Future Expansion

Deepgram continues expanding Nova-3 language support with focus on:
- Additional Southern European languages
- More Southeast Asian languages
- Additional South Asian languages
- Enhanced regional variant support

---

## Resources

- **[Official Deepgram Models & Languages](https://developers.deepgram.com/docs/models-languages-overview)**: Complete language matrix
- **[Language Detection API](https://developers.deepgram.com/docs/language-detection)**: Technical documentation
- **[Keyterm Prompting Guide](https://developers.deepgram.com/docs/smart-format)**: Implementation details
- **[Subgeneratorr README](../README.md)**: Quick start guide
- **[Technical Documentation](technical.md)**: API endpoints and architecture

---

## Summary

Nova-3's 40+ language support with regional variants, universal keyterm prompting, multilingual model, and automatic detection makes Subgeneratorr a flexible subtitle solution for international media libraries.
