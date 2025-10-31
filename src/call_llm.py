"""
Generic LLM caller supporting multiple providers
Supports: OpenAI (GPT-5), Cerebras (Llama 4)
"""
import os

# Try to load dotenv (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Try to import providers
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    from cerebras.cloud.sdk import Cerebras
    HAS_CEREBRAS = True
except ImportError:
    HAS_CEREBRAS = False

class LLMCaller:
    """Generic LLM caller supporting OpenAI and Cerebras"""
    
    def __init__(self, model="gpt-5-2025-08-07", api_key_env="OPENAI_API_KEY"):
        """
        Initialize LLM caller
        
        Args:
            model: Model identifier (e.g., "gpt-5-2025-08-07", "llama-4-scout-17b-16e-instruct")
            api_key_env: Environment variable name for API key
        """
        self.model = model
        self.api_key_env = api_key_env
        self.client = None
        self.provider = None
        self._setup_client()
    
    def _setup_client(self):
        """Setup client based on model and API key"""
        api_key = os.getenv(self.api_key_env)
        
        if not api_key:
            raise Exception(
                f"{self.api_key_env} not found in environment!\n"
                f"Add to .env file: {self.api_key_env}=your_key_here"
            )
        
        # Detect provider based on api_key_env or model
        if "OPENAI" in self.api_key_env or self.model.startswith("gpt"):
            if not HAS_OPENAI:
                raise Exception(
                    "OpenAI library not installed!\n"
                    "Run: pip install openai"
                )
            self.provider = "openai"
            self.client = OpenAI(api_key=api_key)
            print(f"[OK] OpenAI client initialized (model: {self.model})")
            
        elif "CEREBRAS" in self.api_key_env or "llama" in self.model.lower():
            if not HAS_CEREBRAS:
                raise Exception(
                    "Cerebras SDK not installed!\n"
                    "Run: pip install cerebras_cloud_sdk"
                )
            self.provider = "cerebras"
            self.client = Cerebras(api_key=api_key)
            print(f"[OK] Cerebras client initialized (model: {self.model})")
        else:
            raise Exception(
                f"Unable to detect provider for model '{self.model}' and API key '{self.api_key_env}'\n"
                "Please use OPENAI_API_KEY or CEREBRAS_API_KEY"
            )
    
    def call(self, prompt, system_prompt=None, temperature=0.1, max_tokens=None):
        """
        Call LLM with prompt
        
        Args:
            prompt: User prompt text
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum output tokens (None = use model default)
        
        Returns:
            str: LLM response text
        """
        try:
            print(f"[DEBUG] Calling {self.provider.upper()} API...")
            print(f"[DEBUG]   Model: {self.model}")
            print(f"[DEBUG]   Prompt size: {len(prompt):,} chars (~{len(prompt)//4:,} tokens)")
            print(f"[DEBUG]   Temperature: {temperature}")
            if max_tokens:
                print(f"[DEBUG]   Max tokens: {max_tokens:,}")
            
            messages = []
            
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            messages.append({"role": "user", "content": prompt})
            
            kwargs = {
                "messages": messages,
                "model": self.model,
            }
            
            # GPT-5 only supports temperature=1 (default)
            if not self.model.startswith("gpt-5"):
                kwargs["temperature"] = temperature
            
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            
            # Call appropriate provider
            response = self.client.chat.completions.create(**kwargs)
            result = response.choices[0].message.content
            
            print(f"[DEBUG] {self.provider.upper()} response received: {len(result):,} chars")
            return result
            
        except Exception as e:
            print(f"\n{'='*80}")
            print(f"[ERROR] {self.provider.upper()} API CALL FAILED")
            print(f"{'='*80}")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print(f"Model: {self.model}")
            print(f"Prompt size: {len(prompt):,} characters")
            
            # Print full traceback
            import traceback
            print(f"\nFull traceback:")
            traceback.print_exc()
            print(f"{'='*80}\n")
            
            raise  # Re-raise to let caller handle it
    
    def call_with_retry(self, prompt, retries=3, **kwargs):
        """
        Call LLM with automatic retry on failure
        
        Args:
            prompt: User prompt text
            retries: Number of retry attempts
            **kwargs: Additional arguments for call()
        
        Returns:
            str: LLM response text
        
        Raises:
            Exception: If all retries fail
        """
        last_error = None
        
        for attempt in range(retries):
            try:
                return self.call(prompt, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    print(f"[WARNING] Attempt {attempt + 1} failed: {e}. Retrying...")
                continue
        
        raise Exception(f"All {retries} attempts failed. Last error: {last_error}")
