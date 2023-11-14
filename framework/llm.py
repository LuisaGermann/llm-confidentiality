"""library for LLM models, functions and helper stuff"""
import os
from typing import Tuple, Final, Type
import torch
from openai import ChatCompletion
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
    StoppingCriteriaList,
    LogitsProcessorList,
)
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)

from framework.prompts import (
    AttackStopping,
    EosTokenRewardLogitsProcessor,
    STOPPING_LIST,
)

OUTPUT_DIR: Final[str] = "./finetuned_models/"
MAX_RETRIES: int = 10 # number of retries for GPT based chat requests

class LLM():
    """abstract implementation of a genereric LLM model"""
    def __init__(
            self,
            llm_type: str,
            temperature: float = 1.0,
            is_finetuning: bool = False,
            llm_suffix: str = ""
        ) -> None:
        self.llm_suffix: str = llm_suffix
        self.llm_type: str = llm_type

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
            case ("gpt-4" | "gpt-3.5-turbo" | "gpt-4" | "gpt-4-turbo"):
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
                            )
                self.tokenizer.pad_token = self.tokenizer.eos_token

                base_model = AutoModelForCausalLM.from_pretrained(
                            model_name,
                            device_map="auto",
                            low_cpu_mem_usage=True,
                            quantization_config=config,
                            trust_remote_code=True,
                            cache_dir=os.environ["TRANSFORMERS_CACHE"],
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
                )

            case (
                "llama2-7b-prefix" | "llama2-13b-prefix" | "llama2-70b-prefix" 
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

                self.tokenizer = AutoTokenizer.from_pretrained(
                                finetuned_model,
                                use_fast=False,
                                local_files_only=True,
                            )
                self.tokenizer.pad_token = self.tokenizer.eos_token

                base_model = AutoModelForCausalLM.from_pretrained(
                            model_name,
                            device_map="auto",
                            low_cpu_mem_usage=True,
                            quantization_config=config,
                            trust_remote_code=True,
                            cache_dir=os.environ["TRANSFORMERS_CACHE"],
                        )

                self.model = PeftModel.from_pretrained(
                    base_model, # base model
                    finetuned_model, # local peft model
                    device_map="auto",
                    low_cpu_mem_usage=True,
                    torch_dtype=torch.float16,
                    quantization_config=config,
                    local_files_only=True,
                    #return_dict=True,
                    offload_folder=os.environ["TRANSFORMERS_CACHE"],
                )

            case (
                    "llama2" | "llama2-7b" | "llama2-13b" | "llama2-70b" |
                    "llama2-base" | "llama2-7b-base" | "llama2-13b-base" | "llama2-70b-base"
                ):
                self.temperature = max(0.01, min(self.temperature, 5.0))
                # create quantization config
                config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=torch.float16
                )

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

                self.tokenizer = AutoTokenizer.from_pretrained(
                                model_name,
                                use_fast=False,
                                cache_dir=os.environ["TRANSFORMERS_CACHE"],
                            )
                self.tokenizer.pad_token = self.tokenizer.eos_token

                self.model = AutoModelForCausalLM.from_pretrained(
                            model_name,
                            device_map="auto",
                            quantization_config=config,
                            low_cpu_mem_usage=True,
                            trust_remote_code=True,
                            cache_dir=os.environ["TRANSFORMERS_CACHE"],
                        )

            case ("beluga2" | "beluga2-70b" | "beluga-13b" | "beluga-7b"):
                self.temperature = max(0.01, min(self.temperature, 2.0))
                model_name = "stabilityai/"
                # create quantization config
                config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=torch.float16
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


            case ("vicuna" | "vicuna-7b" | "vicuna-13b" | "vicuna-33b"):
                self.temperature = max(0.01, min(self.temperature, 2.0))

                model_name = "lmsys/"
                if self.llm_type.split("-")[1] == "7b":
                    model_name += "vicuna-7b-v1.3"
                elif self.llm_type.split("-")[1] == "13b":
                    model_name += "vicuna-13b-v1.3"
                elif self.llm_type.split("-")[1] == "33b":
                    model_name += "vicuna-33b-v1.3"
                else:
                    model_name += "lmsys/vicuna-33b-v1.3"

                # create quantization config
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
            case _:
                raise NotImplementedError(f"LLM type {self.llm_type} not implemented")


    def __del__(self):
        """Deconstructor for the LLM class"""
        if self.model is not None:
            del self.model
        if self.tokenizer is not None:
            del self.tokenizer


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
            case ("vicuna" | "vicuna-7b" | "vicuna-13b" | "vicuna-33b"):
                formatted_messages = f"""
                {system_prompt}

                USER: {user_prompt}
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
    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_random_exponential(min=1, max=60))
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
            case ("gpt-3.5" | "gpt-3.5-turbo" | "gpt-4" | "gpt-4-turbo"):
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
                if self.llm == "gpt-3":
                    model = "gpt-3.5-turbo"
                elif self.llm == "gpt-4" or self.llm == "gpt-4-turbo":
                    model = "gpt-4-1106-preview"

                completion = ChatCompletion.create(
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
                    "llama2-7b-robust" | "llama2-13b-robust" | "llama2-70b-robust"
                ):
                formatted_messages = self.format_prompt(system_prompt, user_prompt, self.llm_type)

                with torch.no_grad():
                    inputs = self.tokenizer(formatted_messages, return_tensors="pt").to("cuda")
                    stopping_criteria = StoppingCriteriaList([
                        AttackStopping(stops=self.stop_list, tokenizer=self.tokenizer)
                    ])
                    logits_processor = LogitsProcessorList([
                        EosTokenRewardLogitsProcessor(
                            eos_token_id=self.tokenizer.eos_token_id,
                            max_length=2048
                        )
                    ])

                    with torch.backends.cuda.sdp_kernel(enable_flash=True,
                                                        enable_math=False,
                                                        enable_mem_efficient=False):
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
                    "llama2-7b-prefix" | "llama2-13b-prefix" | "llama2-70b-prefix" 
                ):
                formatted_messages = self.format_prompt(system_prompt, user_prompt, self.llm_type)

                with torch.no_grad():
                    inputs = self.tokenizer(formatted_messages, return_tensors="pt").to("cuda")
                    stopping_criteria = StoppingCriteriaList([
                        AttackStopping(stops=self.stop_list, tokenizer=self.tokenizer)
                    ])
                    logits_processor = LogitsProcessorList([
                        EosTokenRewardLogitsProcessor(
                            eos_token_id=self.tokenizer.eos_token_id,
                            max_length=4096
                        )
                    ])

                    model_inputs = {key: val.to("cuda") for key, val in inputs.items()}
                    del inputs

                    with torch.backends.cuda.sdp_kernel(enable_flash=True,
                                                        enable_math=False,
                                                        enable_mem_efficient=False):
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
                    inputs = self.tokenizer(formatted_messages, return_tensors="pt").to("cuda")
                    stopping_criteria = StoppingCriteriaList([
                        AttackStopping(stops=self.stop_list, tokenizer=self.tokenizer)
                    ])
                    logits_processor = LogitsProcessorList([
                        EosTokenRewardLogitsProcessor(
                            eos_token_id=self.tokenizer.eos_token_id,
                            max_length=4096
                        )
                    ])

                    with torch.backends.cuda.sdp_kernel(enable_flash=True,
                                                        enable_math=False,
                                                        enable_mem_efficient=False):
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
                    inputs = self.tokenizer(formatted_messages, return_tensors="pt").to("cuda")
                    stopping_criteria = StoppingCriteriaList([
                        AttackStopping(stops=self.stop_list, tokenizer=self.tokenizer)
                    ])
                    logits_processor = LogitsProcessorList([
                        EosTokenRewardLogitsProcessor(
                            eos_token_id=self.tokenizer.eos_token_id,
                            max_length=4096
                        )
                    ])

                    with torch.backends.cuda.sdp_kernel(enable_flash=True,
                                                        enable_math=False,
                                                        enable_mem_efficient=False):
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
