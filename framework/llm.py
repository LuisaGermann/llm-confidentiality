"""library for LLM models, functions and helper stuff"""
import os
from typing import Tuple, Final, Type, Optional
import torch
from openai import OpenAI

from langchain.tools import BaseTool
from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.utils.function_calling import convert_to_openai_function
from langchain_community.chat_models import ChatOllama
from langchain_experimental.llms.ollama_functions import OllamaFunctions
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
    StoppingCriteriaList,
    LogitsProcessorList,
    GenerationConfig,
    pipeline
)
# from tenacity import (
#     retry,
#     stop_after_attempt,
#     wait_random_exponential,
# )

from framework.prompts import (
    AttackStopping,
    EosTokenRewardLogitsProcessor,
    STOPPING_LIST,
)

OUTPUT_DIR: Final[str] = "./finetuned_models/"
MAX_RETRIES: int = 10 # number of retries for GPT based chat requests

class LLM():
    """Implementation of the LLM class to handle the different LLMs"""
    def __init__(
            self,
            llm_type: str,
            temperature: float = 1.0,
            is_finetuning: bool = False,
            llm_suffix: str = "",
            device: str = "cpu",
            tools: Optional[BaseTool] = None,
            verbose: Optional[bool] = False,
        ) -> None:
        self.llm_suffix: str = llm_suffix
        self.llm_type: str = llm_type
        self.device: str = device
        self.tools: BaseTool = tools
        self.verbose: bool = verbose

        if self.llm_type not in ("gpt-3.5-turbo", "gpt-4"):
            # yes i know this is really dirty, but it does it's job
            from peft import PeftModel

        self.temperature: float = temperature
        self.model: Type[AutoModelForCausalLM] = None
        self.tokenizer: Type[AutoTokenizer] = None
        self.is_finetuning: bool = is_finetuning
        self.stop_list = STOPPING_LIST

        # pre load the models and tokenizer and adjust the temperature
        match self.llm_type:
            case (
                    "llama2-7b-pipe" | "llama2-13b-pipe" | "llama2-70b-pipe"
                ):
                self.temperature = max(0.01, min(self.temperature, 5.0))
                # create quantization config
                if str(self.device) in ["mps", "cpu"]:
                    config=None
                else:
                    config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_compute_dtype=torch.float16
                    )

                # complete the model name for chat or normal models
                model_name = "meta-llama/"
                if "-" not in self.llm_type:
                    raise NotImplementedError(
                        f"LLM specifier {self.llm_type} not complete." +\
                        f"Did you mean {self.llm_type}-7b?"
                    )
                if self.llm_type.split("-")[1] == "7b":
                    model_name += "Llama-2-7b-chat-hf"
                elif self.llm_type.split("-")[1] == "13b":
                    model_name += "Llama-2-13b-chat-hf"
                elif self.llm_type.split("-")[1] == "70b":
                    model_name += "Llama-2-70b-chat-hf"
                else:
                    model_name += "Llama-2-7b-chat-hf"

                self.tokenizer = AutoTokenizer.from_pretrained(
                                model_name,
                                use_fast=False,
                                cache_dir=os.environ["TRANSFORMERS_CACHE"],
                            )
                self.tokenizer.pad_token = self.tokenizer.unk_token

                gen_config = GenerationConfig.from_pretrained(
                        model_name,
                        token=os.environ["HF_TOKEN"],
                        cache_dir=os.environ["TRANSFORMERS_CACHE"],
                    )
                gen_config.max_new_tokens = 2048
                gen_config.temperature = self.temperature
                gen_config.do_sample = True

                self.model = pipeline(
                    "text-generation",
                    model=model_name,
                    tokenizer=self.tokenizer,
                    generation_config=gen_config,
                    device_map="auto",
                    num_return_sequences=1,
                    torch_dtype=torch.float16,
                    do_sample=True,
                    trust_remote_code=True,
                    eos_token_id=self.tokenizer.eos_token_id,
                    # cache_dir=str(Path.home() / "data"),
                    token=os.environ["HF_TOKEN"],
                    # quantization_config=config,
                    # low_cpu_mem_usage=True,
                )


            case ("gemma-2b" | "gemma-7b"):
                self.temperature = max(0.01, min(self.temperature, 5.0))
                # create quantization config
                if str(self.device) in ["mps", "cpu"]:
                    config=None
                else:
                    config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_compute_dtype=torch.float16
                    )

                model_name = "google/"
                if self.llm_type.split("-")[1] == "2b":
                    model_name += "gemma-2b-it"
                elif self.llm_type.split("-")[1] == "7b":
                    model_name += "gemma-7b-it"

                self.tokenizer = AutoTokenizer.from_pretrained(
                                model_name,
                                use_fast=False,
                                cache_dir=os.environ["TRANSFORMERS_CACHE"],
                            )
                self.tokenizer.pad_token = self.tokenizer.unk_token

                self.model = AutoModelForCausalLM.from_pretrained(
                            model_name,
                            device_map="auto",
                            quantization_config=config,
                            low_cpu_mem_usage=True,
                            trust_remote_code=True,
                            cache_dir=os.environ["TRANSFORMERS_CACHE"],
                        )

            case ("orca" | "orca-7b" | "orca-13b" | "orca-70b"):
                self.temperature = max(0.01, min(self.temperature, 5.0))
                # create quantization config
                if str(self.device) in ["mps", "cpu"]:
                    config=None
                else:
                    config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_compute_dtype=torch.float16
                    )

                # complete the model name for chat or normal models
                model_name = "microsoft/"
                if self.llm_type.split("-")[1] == "7b":
                    model_name += "Orca-2-7b"
                elif self.llm_type.split("-")[1] == "13b":
                    model_name += "Orca-2-13b"
                elif self.llm_type.split("-")[1] == "70b":
                    model_name += "Orca-2-70b"
                else:
                    model_name += "Orca-2-7b"

                self.tokenizer = AutoTokenizer.from_pretrained(
                                model_name,
                                use_fast=False,
                                cache_dir=os.environ["TRANSFORMERS_CACHE"],
                            )
                self.tokenizer.pad_token = self.tokenizer.unk_token

                self.model = AutoModelForCausalLM.from_pretrained(
                            model_name,
                            device_map="auto",
                            quantization_config=config,
                            low_cpu_mem_usage=True,
                            trust_remote_code=True,
                            cache_dir=os.environ["TRANSFORMERS_CACHE"],
                        )

            case ("gpt-3.5" | "gpt-3.5-turbo" | "gpt-4" | "gpt-4-turbo"):
                self.temperature = max(0.0, min(self.temperature, 2.0))

            case (
                    "llama2-7b-finetuned" | "llama2-13b-finetuned" | "llama2-70b-finetuned" |
                    "llama2-7b-robust" | "llama2-13b-robust" | "llama2-70b-robust"
                ):
                self.temperature = max(0.01, min(self.temperature, 5.0))
                # complete the model name for chat or normal models
                finetuned_model = OUTPUT_DIR + self.llm_type + self.llm_suffix

                # complete the model name for chat or normal models
                model_name = "meta-llama/"
                if self.llm_type.split("-")[1] == "7b":
                    if "base" in self.llm_type:
                        model_name += "Llama-2-7b-hf"
                    else:
                        model_name += "Llama-2-7b-chat-hf"
                elif self.llm_type.split("-")[1] == "13b":
                    if "base" in self.llm_type:
                        model_name += "Llama-2-13b-hf"
                    else:
                        model_name += "Llama-2-13b-chat-hf"
                elif self.llm_type.split("-")[1] == "70b":
                    if "base" in self.llm_type:
                        model_name += "Llama-2-70b-hf"
                    else:
                        model_name += "Llama-2-70b-chat-hf"
                else:
                    model_name += "Llama-2-70b-chat-hf"

                # if the model is not finetuned, load it in quantized mode
                if not self.is_finetuning:
                    config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_compute_dtype=torch.float16
                    )
                else:
                    config = None

                self.tokenizer = AutoTokenizer.from_pretrained(
                                finetuned_model,
                                use_fast=False,
                                local_files_only=True,
                                token=os.environ["HF_TOKEN"],
                            )
                self.tokenizer.pad_token = self.tokenizer.unk_token

                base_model = AutoModelForCausalLM.from_pretrained(
                            model_name,
                            device_map="auto",
                            low_cpu_mem_usage=True,
                            quantization_config=config,
                            trust_remote_code=True,
                            cache_dir=os.environ["TRANSFORMERS_CACHE"],
                            token=os.environ["HF_TOKEN"],
                        )

                self.model = PeftModel.from_pretrained(
                    base_model, # base model
                    finetuned_model, # local peft model
                    device_map="auto",
                    torch_dtype=torch.float16,
                    quantization_config=config,
                    local_files_only=True,
                    return_dict=True,
                    low_cpu_mem_usage=True,
                    offload_folder=os.environ["TRANSFORMERS_CACHE"],
                    token=os.environ["HF_TOKEN"],
                )
                self.model = self.model.merge_and_unload()

            case (
                "llama2-7b-prefix" | "llama2-13b-prefix" | "llama2-70b-prefix" 
                ):
                self.temperature = max(0.01, min(self.temperature, 5.0))
                # complete the model name for chat or normal models
                finetuned_model = OUTPUT_DIR + self.llm_type + self.llm_suffix

                # complete the model name for chat or normal models
                model_name = "meta-llama/"
                if "-" not in self.llm_type:
                    raise NotImplementedError(
                        f"LLM specifier {self.llm_type} not complete." +\
                        f"Did you mean {self.llm_type}-7b-prefix?"
                    )
                if self.llm_type.split("-")[1] == "7b":
                    if "base" in self.llm_type:
                        model_name += "Llama-2-7b-hf"
                    else:
                        model_name += "Llama-2-7b-chat-hf"
                elif self.llm_type.split("-")[1] == "13b":
                    if "base" in self.llm_type:
                        model_name += "Llama-2-13b-hf"
                    else:
                        model_name += "Llama-2-13b-chat-hf"
                elif self.llm_type.split("-")[1] == "70b":
                    if "base" in self.llm_type:
                        model_name += "Llama-2-70b-hf"
                    else:
                        model_name += "Llama-2-70b-chat-hf"
                else:
                    model_name += "Llama-2-70b-chat-hf"

                # if the model is not finetuned, load it in quantized mode
                if not self.is_finetuning:
                    config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_compute_dtype=torch.float16
                    )

                self.tokenizer = AutoTokenizer.from_pretrained(
                                finetuned_model,
                                use_fast=False,
                                local_files_only=True,
                            )
                self.tokenizer.pad_token = self.tokenizer.unk_token

                base_model = AutoModelForCausalLM.from_pretrained(
                            model_name,
                            device_map="auto",
                            low_cpu_mem_usage=True,
                            quantization_config=config,
                            trust_remote_code=True,
                            cache_dir=os.environ["TRANSFORMERS_CACHE"],
                            token=os.environ["HF_TOKEN"],
                        )

                self.model = PeftModel.from_pretrained(
                    base_model, # base model
                    finetuned_model, # local peft model
                    device_map="auto",
                    low_cpu_mem_usage=True,
                    torch_dtype=torch.float16,
                    quantization_config=config,
                    local_files_only=True,
                    token=os.environ["HF_TOKEN"],
                    offload_folder=os.environ["TRANSFORMERS_CACHE"],
                )

            case (
                    "llama2-7b" | "llama2-13b" | "llama2-70b" |
                    "llama2-7b-base" | "llama2-13b-base" | "llama2-70b-base"
                ):
                self.temperature = max(0.01, min(self.temperature, 5.0))
                # create quantization config
                if str(self.device) in ["mps", "cpu"]:
                    config=None
                else:
                    config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_compute_dtype=torch.float16
                    )

                # complete the model name for chat or normal models
                model_name = "meta-llama/"
                if "-" not in self.llm_type:
                    raise NotImplementedError(
                        f"LLM specifier {self.llm_type} not complete." +\
                        f"Did you mean {self.llm_type}-7b?"
                    )
                if self.llm_type.split("-")[1] == "7b":
                    if "base" in self.llm_type:
                        model_name += "Llama-2-7b-hf"
                    else:
                        model_name += "Llama-2-7b-chat-hf"
                elif self.llm_type.split("-")[1] == "13b":
                    if "base" in self.llm_type:
                        model_name += "Llama-2-13b-hf"
                    else:
                        model_name += "Llama-2-13b-chat-hf"
                elif self.llm_type.split("-")[1] == "70b":
                    if "base" in self.llm_type:
                        model_name += "Llama-2-70b-hf"
                    else:
                        model_name += "Llama-2-70b-chat-hf"
                else:
                    model_name += "Llama-2-70b-chat-hf"

                self.tokenizer = AutoTokenizer.from_pretrained(
                                model_name,
                                use_fast=False,
                                cache_dir=os.environ["TRANSFORMERS_CACHE"],
                            )
                self.tokenizer.pad_token = self.tokenizer.unk_token

                self.model = AutoModelForCausalLM.from_pretrained(
                            model_name,
                            device_map="auto",
                            quantization_config=config,
                            low_cpu_mem_usage=True,
                            trust_remote_code=True,
                            cache_dir=os.environ["TRANSFORMERS_CACHE"],
                        )

            case (
                    "llama3-8b" | "llama3-70b" | "llama3-400b"
                ):
                self.temperature = max(0.01, min(self.temperature, 5.0))
                if self.llm_type.split("-")[1] == "8b":
                    self.model = ChatOllama(model="llama3", temperature=self.temperature)
                elif self.llm_type.split("-")[1] == "70b":
                    self.model = ChatOllama(model="llama3:70b", temperature=self.temperature)
                elif self.llm_type.split("-")[1] == "400b":
                    raise NotImplementedError(f"{self.llm_type} not yet available")
                else:
                    self.model = ChatOllama(model="llama3", temperature=self.temperature)

                self.tokenizer = None

            case (
                    "llama3-8b-tools" | "llama3-70b-tools" | "llama3-400b-tools"
                ):
                self.temperature = max(0.01, min(self.temperature, 5.0))
                if self.llm_type.split("-")[1] == "8b":
                    self.model = OllamaFunctions(
                        model="llama3",
                        temperature=self.temperature,
                        format="json",
                        include_raw=True,
                    )
                elif self.llm_type.split("-")[1] == "70b":
                    self.model = OllamaFunctions(
                        model="llama3:70b",
                        temperature=self.temperature,
                        format="json",
                        include_raw=True,
                    )
                elif self.llm_type.split("-")[1] == "400b":
                    raise NotImplementedError(f"{self.llm_type} not yet available")
                else:
                    self.model = OllamaFunctions(
                        model="llama3",
                        temperature=self.temperature,
                        format="json",
                        include_raw=True,
                    )

                self.tokenizer = None

            case ("beluga2-70b" | "beluga-13b" | "beluga-7b"):
                self.temperature = max(0.01, min(self.temperature, 2.0))
                model_name = "stabilityai/"
                # create quantization config
                if str(self.device) in ["mps", "cpu"]:
                    config=None
                else:
                    config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_compute_dtype=torch.float16
                    )

                if "-" not in self.llm_type:
                    raise NotImplementedError(
                        f"LLM specifier {self.llm_type} not complete." +\
                        f"Did you mean {self.llm_type}-7b?"
                    )
                if self.llm_type.split("-")[1] == "7b":
                    model_name += "StableBeluga-7b"
                elif self.llm_type.split("-")[1] == "13b":
                    model_name += "StableBeluga-13b"
                elif self.llm_type.split("-")[1] == "70b":
                    model_name += "StableBeluga2"
                else:
                    model_name += "StableBeluga2"

                self.tokenizer = AutoTokenizer.from_pretrained(
                                model_name,
                                use_fast=False,
                                cache_dir=os.environ["TRANSFORMERS_CACHE"],
                            )

                self.model = AutoModelForCausalLM.from_pretrained(
                            model_name,
                            device_map="auto",
                            quantization_config=config,
                            low_cpu_mem_usage=True,
                            trust_remote_code=True,
                            cache_dir=os.environ["TRANSFORMERS_CACHE"],
                        )


            case ("vicuna-7b" | "vicuna-13b" | "vicuna-33b"):
                self.temperature = max(0.01, min(self.temperature, 2.0))

                model_name = "lmsys/"
                if "-" not in self.llm_type:
                    raise NotImplementedError(
                        f"LLM specifier {self.llm_type} not complete." +\
                        f"Did you mean {self.llm_type}-7b?"
                    )
                if self.llm_type.split("-")[1] == "7b":
                    model_name += "vicuna-7b-v1.3"
                elif self.llm_type.split("-")[1] == "13b":
                    model_name += "vicuna-13b-v1.3"
                elif self.llm_type.split("-")[1] == "33b":
                    model_name += "vicuna-33b-v1.3"
                else:
                    model_name += "lmsys/vicuna-33b-v1.3"

                # create quantization config
                if str(self.device) in ["mps", "cpu"]:
                    config=None
                else:
                    config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_compute_dtype=torch.float16
                    )

                self.tokenizer = AutoTokenizer.from_pretrained(
                                model_name,
                                use_fast=False,
                                cache_dir=os.environ["TRANSFORMERS_CACHE"],
                            )

                self.model = AutoModelForCausalLM.from_pretrained(
                            model_name,
                            device_map="auto",
                            quantization_config=config,
                            low_cpu_mem_usage=True,
                            trust_remote_code=True,
                            cache_dir=os.environ["TRANSFORMERS_CACHE"],
                        )

            case (
                    "gemma2-9b" | "gemma2-27b"
                ):
                self.temperature = max(0.01, min(self.temperature, 5.0))
                if self.llm_type.split("-")[1] == "9b":
                    self.model = ChatOllama(
                        model="gemma2",
                        temperature=self.temperature,
                    )
                elif self.llm_type.split("-")[1] == "27b":
                    self.model = ChatOllama(
                        model="gemma2:27b",
                        temperature=self.temperature,
                    )
                else:
                    self.model = ChatOllama(
                        model="gemma2",
                        temperature=self.temperature
                    )

                self.tokenizer = None

            case (
                    "gemma2-9b-tool" | "gemma2-27b-tool"
                ):
                self.temperature = max(0.01, min(self.temperature, 5.0))
                if self.llm_type.split("-")[1] == "9b":
                    self.model = OllamaFunctions(
                        model="gemma2",
                        temperature=self.temperature,
                        format="json",
                        include_raw=True,
                    )
                elif self.llm_type.split("-")[1] == "27b":
                    self.model = OllamaFunctions(
                        model="gemma2:27b",
                        temperature=self.temperature,
                        format="json",
                        include_raw=True,
                    )
                else:
                    self.model = OllamaFunctions(
                        model="gemma2",
                        temperature=self.temperature,
                        format="json",
                        include_raw=True,
                    )

                self.tokenizer = None

            case _:
                raise NotImplementedError(f"LLM type {self.llm_type} not implemented")


    def __del__(self):
        """Deconstructor for the LLM class"""
        if self.model is not None:
            del self.model
        if self.tokenizer is not None:
            del self.tokenizer

    def bind_tools_to_model(self, tools: list[callable]) -> None:
        """
        Helper method to bind tools to the LLM

        Parameters:
            tools: List[Callable] - a List of tool functions which should be binded

        Returns:
            None
        """
        self.model.bind_tools(
            [convert_to_openai_function(t) for t in tools],
            tool_choice="any",
        )

    @staticmethod
    def format_prompt(system_prompt: str, user_prompt: str, llm_type: str) -> str:
        """
        Helper method to format the prompt correctly for the different LLMs
        
        Parameters:
            system_prompt: str - the system prompt to initialize the LLM
            user_prompt: str - the user prompt for the LLM to respond on
            llm_type: str - the type of the LLM to format the prompt for

        Returns:
            formatted_prompt: str - the formatted prompt for the LLM
        """

        match llm_type:
            case ("gemma-2b" | "gemma-7b"):
                formatted_messages = f"""<start_of_turn>user
                {system_prompt}{user_prompt}<end_of_turn>
                <start_of_turn>model
                """

            case ("orca2-7b" | "orca2-13b" | "orca2-70b"):
                formatted_messages = f"""<|im_start|>system
                {system_prompt}<|im_end|>
                <|im_start|>user
                {user_prompt}<|im_end|>
                <|im_start|>assistant
                """

            case ("vicuna" | "vicuna-7b" | "vicuna-13b" | "vicuna-33b"):
                formatted_messages = f"""
                {system_prompt}

                USER: {user_prompt}
                """

            case ("llama3" | "llama3-8b" | "llama3-70b" | "llama3-400b"):
                #https://llama.meta.com/docs/model-cards-and-prompt-formats/meta-llama-3/
                formatted_messages = f"""
                <|begin_of_text|><|start_header_id|>system<|end_header_id|>
                {{ {system_prompt} }}<|eot_id|><|start_header_id|>user<|end_header_id|>
                {{ {user_prompt} }}<|eot_id|><|start_header_id|>assistant<|end_header_id|>
                """

            case (
                "llama2" | "llama2-7b" | "llama2-13b" | "llama2-70b" |
                "llama2-base" | "llama2-7b-base" | "llama2-13b-base" | "llama2-70b-base" |
                "llama2-7b-finetuned" | "llama2-13b-finetuned" | "llama2-70b-finetuned" |
                "llama2-7b-robust" | "llama2-13b-robust" | "llama2-70b-robust" |
                "llama2-7b-prefix" | "llama2-13b-prefix" | "llama2-70b-prefix"
                ):
                formatted_messages = f"""<s>[INST] <<SYS>>
                    {system_prompt}
                    <</SYS>>
                    {user_prompt}
                    [/INST]
                    """

            case ("beluga" | "beluga2-70b" | "beluga-13b" | "beluga-7b"):
                formatted_messages = f"""
                ### System:
                {system_prompt}

                ### User:
                {user_prompt}

                ### Assistant:\n
                """

            case _:
                raise NotImplementedError(f"{llm_type} prompt formatting not supported.")

        return formatted_messages

    @torch.inference_mode(mode=True)
    #@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_random_exponential(min=1, max=60))
    def chat(self, system_prompt: str, user_prompt: str) -> Tuple[str, str]:
        """
        predicts a response for a given prompt input 

        Parameters:
            system_prompt: str - the system prompt to initialize the LLM
            user_prompt: str - the user prompt for the LLM to respond on

        Returns:
            response: str - the LLMs' response
            history: str - the LLMs' history with the complete dialoge so far
        """

        match self.llm_type:
            case ("gemma-2b" | "gemma-7b"):
                formatted_messages = self.format_prompt(system_prompt, user_prompt, self.llm_type)
                with torch.no_grad():
                    inputs = self.tokenizer(formatted_messages, return_tensors="pt").to(self.device)

                    outputs = self.model.generate(
                                            inputs=inputs.input_ids,
                                            do_sample=True,
                                            temperature=self.temperature,
                                            max_length=4096,
                                    )
                    response = self.tokenizer.batch_decode(outputs.cpu(), skip_special_tokens=True)
                    del inputs
                    del outputs

                # remove the previous chat history from the response
                # so only the models' actual response remains
                history = "<start_of_turn>"+response[0]+"<end_of_turn>"
                response = response[0].replace(
                    formatted_messages.replace("<start_of_turn>", "").replace("<end_of_turn>", "")
                , "", 1)

            case ("gpt-3.5" | "gpt-3.5-turbo" | "gpt-4" | "gpt-4-turbo"):
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]

                if self.llm_type in ("gpt-3.5", "gpt-3.5-turbo"):
                    model = "gpt-3.5-turbo"
                elif self.llm_type in ("gpt-4", "gpt-4-turbo"):
                    model = "gpt-4"

                client = OpenAI(
                    api_key=os.environ.get("OPENAI_API_KEY"),
                )

                completion = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=self.temperature,
                    seed=1337
                )

                response = completion.choices[0].message.content
                history = f"""<|im_start|>system
                {system_prompt}<|im_end|>
                <|im_start|>user
                {user_prompt}<|im_end|>
                <|im_start|>assistant
                {response}<|im_end|>
                """

            case (
                    "llama2" | "llama2-7b" | "llama2-13b" | "llama2-70b" |
                    "llama2-base" | "llama2-7b-base" | "llama2-13b-base" | "llama2-70b-base" |
                    "llama2-7b-finetuned" | "llama2-13b-finetuned" | "llama2-70b-finetuned" |
                    "llama2-7b-robust" | "llama2-13b-robust" | "llama2-70b-robust" |
                    "orca2-7b" | "orca2-13b" | "orca2-70b"
                ):
                formatted_messages = self.format_prompt(system_prompt, user_prompt, self.llm_type)

                with torch.no_grad():
                    inputs = self.tokenizer(formatted_messages, return_tensors="pt").to(self.device)
                    stopping_criteria = StoppingCriteriaList([
                        AttackStopping(stops=self.stop_list, tokenizer=self.tokenizer)
                    ])
                    logits_processor = LogitsProcessorList([
                        EosTokenRewardLogitsProcessor(
                            eos_token_id=self.tokenizer.eos_token_id,
                            max_length=2048
                        )
                    ])

                    outputs = self.model.generate(
                        inputs=inputs.input_ids,
                        do_sample=True,
                        temperature=self.temperature,
                        max_length=2048,
                        stopping_criteria=stopping_criteria,
                        logits_processor=logits_processor,
                    )
                    response = self.tokenizer.batch_decode(outputs.cpu(), skip_special_tokens=True)
                    del inputs
                    del outputs

                # remove the previous chat history from the response
                # so only the models' actual response remains
                history = "<s>"+response[0]+" </s>"
                response = response[0].replace(formatted_messages.replace("<s>", ""), "", 1)

            case (
                    "llama3" | "llama3-8b" | "llama3-70b" | "llama3-400b" |
                    "gemma2-9b" | "gemma2-27b"
                ):
                prompt = ChatPromptTemplate.from_messages(
                    [
                        ("system", system_prompt),
                        ("human", "{user_prompt}"),
                    ]
                )
                model_chain = prompt | self.model

                response = model_chain.invoke({"user_prompt", user_prompt}).content
                history = system_prompt + user_prompt + response

            case (
                    "llama3-tools" | "llama3-8b-tools" | "llama3-70b-tools" | 
                    "llama3-400b-tools" | "gemma2-9b-tools" | "gemma2-27b-tools"
                ):
                prompt = ChatPromptTemplate.from_messages(
                    [
                        ("system", system_prompt),
                        ("human", "{user_prompt}\n {agent_scratchpad}"),
                    ]
                )
                agent = create_structured_chat_agent(
                    tools=self.tools,
                    llm=self.model,
                    prompt=prompt,
                )

                agent_executor = AgentExecutor(
                    agent=agent,
                    tools=self.tools,
                    handle_parsing_errors=True,
                    verbose=self.verbose,
                )

                response = agent_executor.invoke(
                    {
                        "user_prompt": user_prompt,
                    }
                )["output"]

                if not isinstance(response, str):
                    response = str(response)
                history = system_prompt + user_prompt + response

            case (
                    "llama2-7b-prefix" | "llama2-13b-prefix" | "llama2-70b-prefix" 
                ):
                formatted_messages = self.format_prompt(system_prompt, user_prompt, self.llm_type)

                with torch.no_grad():
                    inputs = self.tokenizer(formatted_messages, return_tensors="pt").to(self.device)
                    stopping_criteria = StoppingCriteriaList([
                        AttackStopping(stops=self.stop_list, tokenizer=self.tokenizer)
                    ])
                    logits_processor = LogitsProcessorList([
                        EosTokenRewardLogitsProcessor(
                            eos_token_id=self.tokenizer.eos_token_id,
                            max_length=4096
                        )
                    ])

                    model_inputs = {key: val.to(self.device) for key, val in inputs.items()}
                    del inputs

                    outputs = self.model.generate(
                        inputs=model_inputs["input_ids"],
                        do_sample=True,
                        temperature=self.temperature,
                        max_length=4096,
                        stopping_criteria=stopping_criteria,
                        logits_processor=logits_processor,
                    )
                    response = self.tokenizer.batch_decode(outputs.cpu(), skip_special_tokens=True)
                    del model_inputs
                    del outputs

                # remove the previous chat history from the response
                # so only the models' actual response remains
                history = "<s>"+response[0]+" </s>"
                response = response[0].replace(formatted_messages.replace("<s>", ""), "", 1)

            case ("beluga2-70b" | "beluga-13b" | "beluga-7b"):
                formatted_messages = self.format_prompt(system_prompt, user_prompt, self.llm_type)

                with torch.no_grad():
                    inputs = self.tokenizer(formatted_messages, return_tensors="pt").to(self.device)
                    stopping_criteria = StoppingCriteriaList([
                        AttackStopping(stops=self.stop_list, tokenizer=self.tokenizer)
                    ])
                    logits_processor = LogitsProcessorList([
                        EosTokenRewardLogitsProcessor(
                            eos_token_id=self.tokenizer.eos_token_id,
                            max_length=4096
                        )
                    ])

                    outputs = self.model.generate(
                        inputs=inputs.input_ids,
                        do_sample=True,
                        temperature=self.temperature,
                        max_length=4096,
                        stopping_criteria=stopping_criteria,
                        logits_processor=logits_processor,
                    )
                    response = self.tokenizer.batch_decode(outputs.cpu(), skip_special_tokens=True)
                    del inputs
                    del outputs

                # remove the previous chat history from the response
                # so only the models' actual response remains
                history = response[0]
                response = response[0].replace(formatted_messages, "", 1)

            case ("vicuna" | "vicuna-7b" | "vicuna-13b" | "vicuna-33b"):
                formatted_messages = self.format_prompt(system_prompt, user_prompt, self.llm_type)

                with torch.no_grad():
                    inputs = self.tokenizer(formatted_messages, return_tensors="pt").to(self.device)
                    stopping_criteria = StoppingCriteriaList([
                        AttackStopping(stops=self.stop_list, tokenizer=self.tokenizer)
                    ])
                    logits_processor = LogitsProcessorList([
                        EosTokenRewardLogitsProcessor(
                            eos_token_id=self.tokenizer.eos_token_id,
                            max_length=4096
                        )
                    ])

                    outputs = self.model.generate(
                        inputs=inputs.input_ids,
                        do_sample=True,
                        temperature=self.temperature,
                        max_length=4096,
                        stopping_criteria=stopping_criteria,
                        logits_processor=logits_processor,
                    )
                    response = self.tokenizer.batch_decode(outputs.cpu(), skip_special_tokens=True)
                    del inputs
                    del outputs

                # remove the previous chat history from the response
                # so only the models' actual response remains
                history = response[0]
                response = response[0].replace(formatted_messages, "", 1)

            case _:
                raise NotImplementedError(f"LLM type {self.llm_type} not implemented")

        return (response, history)
