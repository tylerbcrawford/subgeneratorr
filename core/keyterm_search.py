#!/usr/bin/env python3
"""
LLM-powered keyterm generation for Deepgram transcription accuracy.

This module provides intelligent keyterm generation using Large Language Models
(Anthropic Claude or OpenAI GPT) to analyze show/movie metadata and generate
contextually relevant keyterms that improve transcription accuracy up to 90%.
"""

from typing import List, Optional, Dict, Any
from pathlib import Path
from enum import Enum
import os

from core.media_metadata import MediaMetadata, format_metadata_for_prompt


class LLMProvider(Enum):
    """Supported LLM providers."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"


class LLMModel(Enum):
    """Supported LLM models with their API identifiers."""
    # Anthropic models (Claude 4.6 series)
    CLAUDE_SONNET_4_6 = "claude-sonnet-4-6"
    CLAUDE_HAIKU_4_5 = "claude-haiku-4-5"

    # OpenAI models (GPT-4.1 series - non-reasoning, low latency)
    GPT_4_1 = "gpt-4.1"
    GPT_4_1_MINI = "gpt-4.1-mini"

    # Google models (Gemini 2.5 series)
    GEMINI_2_5_FLASH = "gemini-2.5-flash"


# Model pricing (per 1M tokens) - as of 2026-02
MODEL_PRICING = {
    LLMModel.CLAUDE_SONNET_4_6: {"input": 3.00, "output": 15.00},
    LLMModel.CLAUDE_HAIKU_4_5: {"input": 1.00, "output": 5.00},
    LLMModel.GPT_4_1: {"input": 2.00, "output": 8.00},
    LLMModel.GPT_4_1_MINI: {"input": 0.40, "output": 1.60},
    LLMModel.GEMINI_2_5_FLASH: {"input": 0.30, "output": 2.50},
}


# Keyterm generation prompt template for TV shows
KEYTERM_PROMPT_TV_TEMPLATE = """You are assisting with audio transcription accuracy by generating a keyterm list for Deepgram Nova-3 API's keyterm prompting feature.

TASK:
Research the following TV show and create a focused list of keyterms that will improve transcription accuracy across THE ENTIRE SERIES:

{media_info}

{existing_keyterms_section}

IMPORTANT: Generate keyterms for the ENTIRE SHOW (all seasons/episodes), not just a single episode. The context above helps you identify the correct show and verify your research, but the keyterms should cover the whole series.

CORE PRINCIPLE:
Every keyterm MUST be a word or phrase that characters actually SAY in dialogue or that a narrator speaks aloud. These keyterms help the speech-to-text engine recognize spoken words — if it wouldn't appear in a subtitle file, it does NOT belong in this list.

SEARCH REQUIREMENTS:
Search for information using reliable, authoritative sources such as:
- IMDb (Internet Movie Database)
- Wikipedia and Fandom wikis
- TV databases (TMDB, TheTVDB)
- Fan wikis for character and terminology lists
- Show summaries and cast information

KEYTERMS TO IDENTIFY (Priority Order):
1. Character names spoken in dialogue (first names, last names, nicknames, aliases)
   - Full names AND the forms characters actually use: "Heisenberg", "Cap'n Cook", "Skyler"
   - Prioritize names that sound like common words or might be misheard
   - Example: "Gus Fring" (might be heard as "Gus frying")
2. Proper nouns spoken aloud: place names, business names, brand names
   - Example: "Los Pollos Hermanos", "Albuquerque", "Madrigal"
3. Show-specific vocabulary that characters use in dialogue
   - Invented words, jargon, slang, or technical terms specific to the show's world
   - Example: "methylamine", "ricin", "Pollos"
4. Catchphrases, recurring spoken phrases, or proper-noun phrases
   - Example: "Better call Saul", "Yeah, science!"

CRITICAL FORMATTING RULES:
- Proper nouns (names, places, titles): Use appropriate capitalization
  Examples: "Walter White", "Los Pollos Hermanos", "Heisenberg"
- Common nouns and technical terms: Use lowercase
  Examples: "methylamine", "ricin"
- Multi-word phrases: Maintain natural capitalization
  Examples: "New Mexico", "Better call Saul"

WHAT TO AVOID:
- Common English words the speech engine already handles well (e.g., "cartel", "murder", "police", "hospital")
- Thematic or abstract concepts that aren't spoken as specific terms (e.g., "moral ambiguity", "power dynamics")
- Behind-the-scenes or production terminology viewers wouldn't hear in dialogue
- Visual elements, props, or plot devices that aren't referred to by name in speech
- Generic genre terms (e.g., "crime drama", "thriller", "suspense")
- Words that Deepgram's base model already transcribes accurately

QUANTITY LIMIT:
Generate ONLY the 20-50 most critical terms that are:
- Actually spoken by characters or narrators in the show
- Most likely to be misheard, misspelled, or confused with other words
- Proper nouns, unusual names, or show-specific vocabulary

The 500 token limit means quality over quantity - prioritize terms with highest potential for transcription errors.

OUTPUT FORMAT:
Provide ONLY a simple comma-separated list of keyterms with proper capitalization. Do not include headers, context notes, or explanations.

Example format:
Walter White,Jesse Pinkman,Heisenberg,Gus Fring,Skyler,Hank Schrader,Saul Goodman,Los Pollos Hermanos,Albuquerque,methylamine,ricin,Madrigal,Tuco Salamanca

Begin your research and generate the keyterm list now."""


# Keyterm generation prompt template for movies
KEYTERM_PROMPT_MOVIE_TEMPLATE = """You are assisting with audio transcription accuracy by generating a keyterm list for Deepgram Nova-3 API's keyterm prompting feature.

TASK:
Research the following movie and create a focused list of keyterms that will improve transcription accuracy:

{media_info}

{existing_keyterms_section}

CORE PRINCIPLE:
Every keyterm MUST be a word or phrase that characters actually SAY in dialogue or that a narrator speaks aloud. These keyterms help the speech-to-text engine recognize spoken words — if it wouldn't appear in a subtitle file, it does NOT belong in this list.

SEARCH REQUIREMENTS:
Search for information using reliable, authoritative sources such as:
- IMDb (Internet Movie Database)
- Wikipedia and Fandom wikis
- Official production websites and press materials
- Entertainment databases (TMDB)
- Reviews from major publications (if they contain character/term lists)

KEYTERMS TO IDENTIFY (Priority Order):
1. Character names spoken in dialogue (first names, last names, nicknames, aliases)
   - Full names AND the forms characters actually use: "Cobb", "Mr. Charles"
   - Prioritize names that sound like common words or might be misheard
   - Example: "Cobb" (might be heard as "cop"), "Ariadne", "Saito"
2. Proper nouns spoken aloud: place names, company names, fictional locations
   - Example: "Mombasa", "Limbo", "Proclus Global"
3. Movie-specific vocabulary that characters use in dialogue
   - Invented words, jargon, or technical terms from the movie's world
   - Example: "totem", "extraction", "kick"
4. Catchphrases, recurring spoken phrases, or proper-noun phrases
   - Example: "dream within a dream", "inception"

CRITICAL FORMATTING RULES:
- Proper nouns (names, places, titles): Use appropriate capitalization
  Examples: "Dom Cobb", "Ariadne", "Proclus Global"
- Common nouns and technical terms: Use lowercase
  Examples: "totem", "extraction", "kick"
- Multi-word phrases: Maintain natural capitalization
  Examples: "Mr. Charles", "dream within a dream"

WHAT TO AVOID:
- Common English words the speech engine already handles well (e.g., "dream", "sleep", "target", "architect")
- Thematic or abstract concepts that aren't spoken as specific terms (e.g., "subconscious guilt", "reality vs. dream")
- Behind-the-scenes or production terminology viewers wouldn't hear in dialogue
- Visual elements, props, or set pieces that aren't referred to by name in speech
- Generic genre terms (e.g., "sci-fi", "heist", "thriller")
- Words that Deepgram's base model already transcribes accurately

QUANTITY LIMIT:
Generate ONLY the 20-50 most critical terms that are:
- Actually spoken by characters or narrators in the movie
- Most likely to be misheard, misspelled, or confused with other words
- Proper nouns, unusual names, or movie-specific vocabulary

The 500 token limit means quality over quantity - prioritize terms with highest potential for transcription errors.

OUTPUT FORMAT:
Provide ONLY a simple comma-separated list of keyterms with proper capitalization. Do not include headers, context notes, or explanations.

Example format:
Dom Cobb,Ariadne,Eames,Arthur,Mal,Saito,Yusuf,Fischer,Proclus Global,Mombasa,totem,extraction,inception,limbo,kick,Mr. Charles

Begin your research and generate the keyterm list now."""


class KeytermSearcher:
    """Generate contextually relevant keyterms using LLM analysis."""
    
    def __init__(self, provider: LLMProvider, model: LLMModel, api_key: str):
        """
        Initialize KeytermSearcher with LLM configuration.
        
        Args:
            provider: LLM provider (Anthropic or OpenAI)
            model: Specific model to use
            api_key: API key for the provider
        
        Raises:
            ValueError: If provider/model combination is invalid
        """
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self._client = None
        
        # Validate provider/model combination
        if provider == LLMProvider.ANTHROPIC:
            if model not in [LLMModel.CLAUDE_SONNET_4_6, LLMModel.CLAUDE_HAIKU_4_5]:
                raise ValueError(f"Model {model} not valid for provider {provider}")
        elif provider == LLMProvider.OPENAI:
            if model not in [LLMModel.GPT_4_1, LLMModel.GPT_4_1_MINI]:
                raise ValueError(f"Model {model} not valid for provider {provider}")
        elif provider == LLMProvider.GOOGLE:
            if model not in [LLMModel.GEMINI_2_5_FLASH]:
                raise ValueError(f"Model {model} not valid for provider {provider}")
    
    def generate_from_metadata(
        self,
        metadata: MediaMetadata,
        existing_keyterms: Optional[List[str]] = None,
        preserve_existing: bool = False
    ) -> Dict[str, Any]:
        """
        Generate keyterms from show/movie metadata using LLM.

        Args:
            metadata: MediaMetadata object with show/movie information
            existing_keyterms: Optional list of existing keyterms
            preserve_existing: If True, merge with existing; if False, overwrite

        Returns:
            Dict containing:
                - keyterms: List[str] - Generated keyterms
                - token_count: int - Total tokens used
                - estimated_cost: float - Cost in USD
                - provider: str - LLM provider used
                - model: str - Model used

        Raises:
            Exception: If LLM API call fails
        """
        # Build prompt
        prompt = self._build_prompt(metadata, existing_keyterms, preserve_existing)
        
        # Call appropriate LLM provider
        if self.provider == LLMProvider.ANTHROPIC:
            response_text, input_tokens, output_tokens = self._call_anthropic(prompt)
        elif self.provider == LLMProvider.OPENAI:
            response_text, input_tokens, output_tokens = self._call_openai(prompt)
        elif self.provider == LLMProvider.GOOGLE:
            response_text, input_tokens, output_tokens = self._call_google(prompt)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        # Parse response into keyterms
        keyterms = self._parse_response(response_text)

        # If preserving existing, merge them
        if preserve_existing and existing_keyterms:
            # Add existing keyterms that aren't already in the new list
            new_lower = {k.lower() for k in keyterms}

            for existing in existing_keyterms:
                if existing.lower() not in new_lower:
                    keyterms.append(existing)

        # Calculate cost using actual token counts from API response
        token_count = input_tokens + output_tokens
        cost = self._calculate_cost(input_tokens, output_tokens)

        return {
            'keyterms': keyterms,
            'token_count': token_count,
            'estimated_cost': cost,
            'provider': self.provider.value,
            'model': self.model.value
        }
    
    def estimate_cost(self, metadata: MediaMetadata) -> Dict[str, Any]:
        """
        Estimate cost before making LLM request.

        Args:
            metadata: MediaMetadata object with show/movie information

        Returns:
            Dict containing:
                - estimated_tokens: int - Estimated tokens
                - estimated_cost: float - Estimated cost in USD
                - model: str - Model that will be used
        """
        # Build prompt to estimate token count
        prompt = self._build_prompt(metadata)

        # Rough token estimation: ~1 token per 4 characters
        input_tokens = len(prompt) // 4

        # Estimated response tokens (20-50 keyterms, ~200 tokens)
        output_tokens = 200

        cost = self._calculate_cost(input_tokens, output_tokens)

        return {
            'estimated_tokens': input_tokens + output_tokens,
            'estimated_cost': cost,
            'model': self.model.value
        }
    
    def _build_prompt(
        self,
        metadata: MediaMetadata,
        existing_keyterms: Optional[List[str]] = None,
        preserve_existing: bool = False
    ) -> str:
        """
        Build the LLM prompt from template and context.

        Args:
            metadata: MediaMetadata object with show/movie information
            existing_keyterms: Optional list of existing keyterms
            preserve_existing: If True, instruct to preserve; if False, use as reference

        Returns:
            Complete prompt string
        """
        # Build existing keyterms section
        existing_section = self._build_existing_keyterms_section(
            existing_keyterms,
            preserve_existing
        )

        # Format media info for prompt
        media_info = format_metadata_for_prompt(metadata)

        # Choose appropriate template based on media type
        if metadata.media_type == 'tv':
            template = KEYTERM_PROMPT_TV_TEMPLATE
        else:
            template = KEYTERM_PROMPT_MOVIE_TEMPLATE

        # Format the template
        prompt = template.format(
            media_info=media_info,
            existing_keyterms_section=existing_section
        )

        return prompt
    
    def _build_existing_keyterms_section(
        self, 
        existing: Optional[List[str]] = None, 
        preserve: bool = False
    ) -> str:
        """
        Build section for existing keyterms in prompt.
        
        Args:
            existing: Optional list of existing keyterms
            preserve: If True, instruct to preserve; if False, use as reference
        
        Returns:
            Formatted section string or empty string
        """
        if not existing:
            return ""
        
        keyterms_list = ', '.join(existing)
        
        if preserve:
            return f"""EXISTING KEYTERMS TO PRESERVE:
The following keyterms are already defined and should be included in your response:
{keyterms_list}

Your task is to ADD NEW keyterms that complement these existing ones. Include all existing keyterms in your output."""
        else:
            return f"""REFERENCE KEYTERMS:
The following keyterms were previously used (for reference only):
{keyterms_list}

Feel free to use these as inspiration but generate a fresh, optimized list."""
    
    def _parse_response(self, response: str) -> List[str]:
        """
        Parse LLM response into list of keyterms.

        Handles models that return extraneous content like markdown headers,
        research summaries, or explanatory paragraphs by stripping non-keyterm
        lines before parsing the comma-separated list.

        Args:
            response: Raw LLM response text

        Returns:
            List of parsed keyterms
        """
        import re

        response = response.strip()

        # Strip markdown fences (```...```)
        response = re.sub(r'```[\s\S]*?```', '', response)

        # Remove lines that look like headers or commentary, not keyterms:
        #   - Markdown headers (# ...)
        #   - Lines starting with ** (bold labels like **Research:** ...)
        #   - Lines that are clearly sentences (>80 chars with multiple spaces)
        #   - Blank lines
        cleaned_lines = []
        for line in response.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith('#'):
                continue
            if stripped.startswith('**') and ':' in stripped:
                continue
            if re.match(r'^(Note|Here|These|The following|Research|Summary|I )', stripped, re.IGNORECASE):
                continue
            cleaned_lines.append(stripped)

        response = ' '.join(cleaned_lines)

        # Split by comma
        keyterms = [term.strip() for term in response.split(',')]

        # Filter out empty, too-long (not a keyterm), and duplicate terms
        seen = set()
        unique_keyterms = []

        for term in keyterms:
            # Strip surrounding quotes or asterisks
            term = term.strip('"\'*`')
            if not term:
                continue
            # Skip terms that are clearly sentences (>60 chars)
            if len(term) > 60:
                continue
            if term.lower() not in seen:
                seen.add(term.lower())
                unique_keyterms.append(term)

        return unique_keyterms
    
    def _call_anthropic(self, prompt: str) -> tuple[str, int, int]:
        """
        Make API call to Anthropic Claude.

        Args:
            prompt: Formatted prompt string

        Returns:
            Tuple of (response_text, input_tokens, output_tokens)

        Raises:
            Exception: If API call fails
        """
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package not installed. Install with: pip install anthropic>=0.30.0"
            )
        
        # Initialize client if needed
        if not self._client:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        
        try:
            # Make API call
            message = self._client.messages.create(
                model=self.model.value,
                max_tokens=500,  # Limited for keyterm lists
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract response text
            if not message.content:
                raise Exception("Anthropic API returned empty response — no content blocks")
            response_text = message.content[0].text
            
            return response_text, message.usage.input_tokens, message.usage.output_tokens

        except Exception as e:
            error_str = str(e)
            if 'rate_limit' in error_str.lower() or '429' in error_str:
                raise Exception("Anthropic API rate limit exceeded — wait a moment and try again")
            elif '401' in error_str or 'authentication' in error_str.lower():
                raise Exception("Anthropic API key is invalid or expired")
            else:
                brief = error_str.split('\n')[0][:200]
                raise Exception(f"Anthropic API error: {brief}")

    def _call_openai(self, prompt: str) -> tuple[str, int, int]:
        """
        Make API call to OpenAI GPT.

        Args:
            prompt: Formatted prompt string

        Returns:
            Tuple of (response_text, input_tokens, output_tokens)

        Raises:
            Exception: If API call fails
        """
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package not installed. Install with: pip install openai>=1.35.0"
            )
        
        # Initialize client if needed
        if not self._client:
            self._client = openai.OpenAI(api_key=self.api_key)
        
        try:
            response = self._client.chat.completions.create(
                model=self.model.value,
                max_tokens=500,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that generates keyterm lists for transcription accuracy."},
                    {"role": "user", "content": prompt}
                ]
            )

            if not response.choices:
                raise Exception("OpenAI API returned empty response — no choices")
            response_text = response.choices[0].message.content

            return response_text, response.usage.prompt_tokens, response.usage.completion_tokens

        except Exception as e:
            error_str = str(e)
            if 'rate_limit' in error_str.lower() or '429' in error_str:
                raise Exception("OpenAI API rate limit exceeded — wait a moment and try again")
            elif '401' in error_str or 'authentication' in error_str.lower():
                raise Exception("OpenAI API key is invalid or expired")
            elif 'insufficient_quota' in error_str.lower():
                raise Exception("OpenAI API quota exceeded — check your billing plan")
            else:
                brief = error_str.split('\n')[0][:200]
                raise Exception(f"OpenAI API error: {brief}")

    def _call_google(self, prompt: str) -> tuple[str, int, int]:
        """
        Make API call to Google Gemini.

        Args:
            prompt: Formatted prompt string

        Returns:
            Tuple of (response_text, input_tokens, output_tokens)

        Raises:
            Exception: If API call fails
        """
        try:
            from google import genai
        except ImportError:
            raise ImportError(
                "google-genai package not installed. Install with: pip install google-genai>=1.0.0"
            )

        # Initialize client if needed
        if not self._client:
            self._client = genai.Client(api_key=self.api_key)

        try:
            from google.genai import types as genai_types

            response = self._client.models.generate_content(
                model=self.model.value,
                contents=prompt,
                config={
                    "max_output_tokens": 2048,
                    "system_instruction": "You are a helpful assistant that generates keyterm lists for transcription accuracy.",
                    # Cap thinking tokens so they don't consume the output budget.
                    # Gemini 2.5 models use "thinking" tokens that count against
                    # max_output_tokens — without this cap, thinking can consume
                    # 1900+ tokens, leaving <100 for the actual response.
                    "thinking_config": genai_types.ThinkingConfig(thinking_budget=1024),
                },
            )

            response_text = response.text

            input_tokens = response.usage_metadata.prompt_token_count
            output_tokens = response.usage_metadata.candidates_token_count

            return response_text, input_tokens, output_tokens

        except Exception as e:
            error_str = str(e)
            # Extract a clean message from verbose API errors
            if 'RESOURCE_EXHAUSTED' in error_str:
                raise Exception("Gemini API quota exceeded — try a different model or check your billing plan")
            elif '401' in error_str or 'UNAUTHENTICATED' in error_str:
                raise Exception("Gemini API key is invalid or expired")
            elif '403' in error_str or 'PERMISSION_DENIED' in error_str:
                raise Exception("Gemini API key lacks permission for this model")
            else:
                # Keep it short — strip the nested JSON
                brief = error_str.split('\n')[0][:200]
                raise Exception(f"Gemini API error: {brief}")

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate cost based on separate input/output token counts.

        Args:
            input_tokens: Number of input (prompt) tokens
            output_tokens: Number of output (completion) tokens

        Returns:
            Cost in USD
        """
        pricing = MODEL_PRICING.get(self.model)
        if not pricing:
            return 0.0

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost