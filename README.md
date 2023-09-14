# Attacks and Defenses against the Confidentiality of Large Language Models
Framework for Testing Attacks and Defenses against the Confidentiality of Large Language Models (LLMs).

<b>!! This project will most likely only work on Linux systems with NVIDIA-GPUs and CUDA installed !!</b>

## Setup
Before running the code, install the requirements:
```
python -m pip install -U -r requirements.txt
```
Create both a ```key.txt``` file containing your OpenAI API key as well as a ```hf_token.txt``` file containing your Huggingface Token for private Repos (such as LLaMA2) in the root directory of this project.

## Usage
```
python run.py [-h] [-a | --attacks [ATTACK1, ATTACK2, ..]] [-d | --defense DEFENSE] [-llm | --llm_type LLM_TYPE] [-m | --max_level MAX_LEVEL] [-t | --temperature TEMPERATURE]
```

## Example Usage
```python
python run.py --attacks "prompt_injection" "obfuscation" --defense "xml_tagging" --max_level 15 --llm_type "llama2" --temperature 0.7
```

## Arguments
| Argument | Type | Default Value | Description |
|----------|------|---------------|-------------|
| ```-h, --help``` | - | - | show this help message and exit |
| ```-a, --attacks``` | <b>List[str]</b> | ```payload_splitting``` | specifies the attacks which will be utilized against the LLM |
| ```-d, --defense``` | <b>str</b> | ```None``` | specifies the defense for the LLM |
| ```-llm, --llm_type``` | <b>str</b> | ```gpt-3.5-turbo``` | specifies the type of opponent |
| ```-t, --temperature``` | <b>float</b> | ```0.0``` | specifies the temperature for the LLM to control the randomness |
| ```-cd, --create_dataset``` | <b>bool</b> | ```False``` | specifies whether a new dataset of enhanced system prompts should be created |
| ```-i, --iterations``` | <b>int</b> | ```10``` | specifies the number of iterations for the attack |
| ```-n, --name_suffix``` | <b>str</b> | ```""``` | Specifies a name suffix to load custom models. Since argument parameter strings aren't allowed to start with '-' symbols, the first '-' will be added by the parser automatically |

The naming conventions for the models are as follows:
```python
<model_name>-<param_count>-<robustness>-<attack_suffix>-<custom_suffix>
```
e.g.:
```python
LLaMA2-7b-robust-prompt_injection-0613
```


## Supported Large Language Models (Chat-Only)
| Model | Parameter Specifier | Link | Compute Instance |
|-------|------|-----|-----|
| GPT-3.5-Turbo | ```gpt-3.5-turbo``` / ```gpt-3.5-turbo-0301``` / ```gpt-3.5-turbo-0613``` | [Link](https://platform.openai.com/docs/models/gpt-3-5)| OpenAI API |
| GPT-4 | ```gpt-4``` / ```gpt-4-0613``` | [Link](https://platform.openai.com/docs/models/gpt-4)| OpenAI API |
| LLaMA2 (chat) | ```llama2-7b``` / ```llama2-13b``` / ```llama2-70b``` | [Link](https://huggingface.co/meta-llama) | Local Inference |
| LLaMA2 (base) | ```llama2-7b-base``` / ```llama2-13b-base``` / ```llama2-70b-base``` | [Link](https://huggingface.co/meta-llama) | Local Inference |
| LLaMA2 (chat) Finetuned | ```llama2-7b-finetuned``` / ```llama2-13b-finetuned``` / ```llama2-70b-finetuned``` | [Link](https://huggingface.co/meta-llama) | Local Inference |
| LLaMA2 (chat) hardened | ```llama2-7b-robust``` / ```llama2-13b-robust``` / ```llama2-70b-robust```|  [Link](https://huggingface.co/meta-llama) | Local Inference |
| Vicuna | ```vicuna-7b``` / ```vicuna-13b``` / ```vicuna-33b``` | [Link](https://huggingface.co/lmsys/vicuna-33b-v1.3) | Local Inference |
| StableBeluga (2) | ```beluga-7b``` / ```beluga-13b``` / ```beluga2-70b```| [Link](https://huggingface.co/stabilityai/StableBeluga2) | Local Inference |

(Finetuned or robust/hardened LLaMA models first have to be generated using the ```finetuning.py``` script, see below)

## Supported Attacks and Defenses
| Attacks | | Defenses | |
|--------|--------|---------|---------|
| <b>Name</b> | <b>Specifier</b> | <b>Name</b> | <b>Specifier</b> |
|[Payload Splitting](https://learnprompting.org/docs/prompt_hacking/offensive_measures/payload_splitting) | ```payload_splitting``` | [Random Sequence Enclosure](https://learnprompting.org/docs/prompt_hacking/defensive_measures/random_sequence) | ```seq_enclosure``` |
|[Obfuscation](https://learnprompting.org/docs/prompt_hacking/offensive_measures/obfuscation) | ```obfuscation``` |[XML Tagging](https://learnprompting.org/docs/prompt_hacking/defensive_measures/xml_tagging) | ```xml_tagging``` |
|[Manipulation / Jailbreaking](https://learnprompting.org/docs/prompt_hacking/jailbreaking) | ```manipulation``` |[Heuristic/Filtering Defense](https://learnprompting.org/docs/prompt_hacking/defensive_measures/filtering) | ```heuristic_defense``` |
|Translation | ```translation``` |[Sandwich Defense](https://learnprompting.org/docs/prompt_hacking/defensive_measures/sandwich_defense) | ```sandwiching``` |
|[ChatML Abuse](https://www.robustintelligence.com/blog-posts/prompt-injection-attack-on-gpt-4) | ```chatml_abuse``` | [LLM Evaluation](https://learnprompting.org/docs/prompt_hacking/defensive_measures/llm_eval) | ```llm_eval``` |
|[Masking](https://learnprompting.org/docs/prompt_hacking/offensive_measures/obfuscation) | ```masking``` | |
|[Typoglycemia](https://twitter.com/lauriewired/status/1682825103594205186?s=20) | ```typoglycemia``` | |
|[Adversarial Suffix](https://llm-attacks.org/) | ```advs_suffix``` | |

# Finetuning to harden LLMs against attacks or create enhanced system prompts
This section covers the possible LLaMA2 finetuning options. The first finetuning options is on a dataset consisting of system prompts to safely instruct an LLM to keep a secret key safe. The second finetuning option (using the ```--train_robust``` option) is using system prompts and adversarial prompts to harden the model against prompt injection attacks.

## Setup
Additionally to the above setup run
```bash
accelerate config
```
to configure the distributed training capabilities of your system. And
```bash
wandb login
```
with your WandB API key to enable logging of the finetuning process.

## Usage
```python
python finetuning.py [-h] [-llm | --llm_type LLM_NAME] [-i | --iterations ITERATIONS] [-tr | --train_robust TRAIN_ROBUST]
```

# Arguments
| Argument | Type | Default Value | Description |
|----------|------|---------------|-------------|
| ```-h, --help``` | - | - | Show this help message and exit |
| ```-llm, --llm_type``` | <b>str</b> | ```llama2-7b``` |Specifies the type of llm to finetune |
| ```-i, --iterations``` | <b>int</b> | ```1000``` | Specifies the number of iterations for the finetuning |
| ```-tr, --train_robust``` | <b>bool</b> | ```False``` | Enable robustness finetuning |
| ```-a, --attacks``` | <b>List[str]</b> | ```payload_splitting``` | Specifies the attacks which will be used to harden the llm during finetuning. Only has an effect if ```--train_robust``` is set to True. For supported attacks see the previous section |
| ```-n, --name_suffix``` | <b>str</b> | ```""``` | Specifies a suffix for the finetuned model name |


## Supported Large Language Models (base)
| Model | Parameter Specifier | Link | Compute Instance |
|-------|------|-----|-----|
| LLaMA2 (base) | ```llama2-7b``` / ```llama2-13b``` / ```llama2-70b``` | [Link](https://huggingface.co/meta-llama) | Local Inference |

