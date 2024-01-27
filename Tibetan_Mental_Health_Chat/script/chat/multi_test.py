# -- coding: utf-8 --
# @time :
# @author : shajiu
# @email : 18810979033@163.com
# @file : .py
# @software: pycharm
from transformers import AutoTokenizer
import torch

import sys
sys.path.append("../../")
from component.utils import ModelUtils
import json


def main(input_file):
    # 使用合并后的模型进行推理
    model_name_or_path = '/home/zhumx/code/Firefly-master/output/firefly-llama2-7b-qlora-sft-merge'
    #model_name_or_path = "/home/zhumx/code/model/llama2-7b-chat"
    adapter_name_or_path = None

    # 使用base model和adapter进行推理
    # model_name_or_path = 'baichuan-inc/Baichuan-7B'
    # adapter_name_or_path = 'YeungNLP/firefly-baichuan-7b-qlora-sft'

    # 是否使用4bit进行推理，能够节省很多显存，但效果可能会有一定的下降
    load_in_4bit = False
    device = 'cuda'

    # 生成超参配置
    max_new_tokens = 500  # 每轮对话最多生成多少个token
    history_max_len = 1000  # 模型记忆的最大token长度
    top_p = 0.9
    temperature = 0.35
    repetition_penalty = 1.0

    # 加载模型
    model = ModelUtils.load_model(
        model_name_or_path,
        load_in_4bit=load_in_4bit,
        adapter_name_or_path=adapter_name_or_path
    ).eval()
    # 加载tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        model_name_or_path,
        trust_remote_code=True,
        # llama不支持fast
        use_fast=False if model.config.model_type == 'llama' else True
    )
    # QWenTokenizer比较特殊，pad_token_id、bos_token_id、eos_token_id均为None。eod_id对应的token为<|endoftext|>
    if tokenizer.__class__.__name__ == 'QWenTokenizer':
        tokenizer.pad_token_id = tokenizer.eod_id
        tokenizer.bos_token_id = tokenizer.eod_id
        tokenizer.eos_token_id = tokenizer.eod_id



    # 开始对话
    utterance_id = 0    # 记录当前是第几轮对话，为了契合chatglm的数据组织格式
    with open(input_file, 'r', encoding="utf-8") as input_file:
        for index,line in enumerate(input_file.readlines()):
            #if index>137:
            conversation = json.loads(line.strip()).get("conversation")
            # 记录所有历史记录
            if model.config.model_type != 'chatglm':
                history_token_ids = torch.tensor([[tokenizer.bos_token_id]], dtype=torch.long)
            else:
                history_token_ids = torch.tensor([[]], dtype=torch.long)
            res=list()
            for val in conversation:
                assistant = ""
                for key in val:
                    if key == "human":
                        user_input =val.get(key)
                        utterance_id += 1
                        # chatglm使用官方的数据组织格式
                        if model.config.model_type == 'chatglm':
                            user_input = '[Round {}]\n\n问：{}\n\n答：'.format(utterance_id, user_input)
                            user_input_ids = tokenizer(user_input, return_tensors="pt", add_special_tokens=False).input_ids
                        # firefly的数据组织格式
                        # 为了兼容qwen-7b，因为其对eos_token进行tokenize，无法得到对应的eos_token_id
                        else:
                            input_ids = tokenizer(user_input, return_tensors="pt", add_special_tokens=False).input_ids
                            eos_token_id = torch.tensor([[tokenizer.eos_token_id]], dtype=torch.long)
                            user_input_ids = torch.concat([input_ids, eos_token_id], dim=1)
                        history_token_ids = torch.concat((history_token_ids, user_input_ids), dim=1)
                        model_input_ids = history_token_ids[:, -history_max_len:].to(device)
                        with torch.no_grad():
                            outputs = model.generate(
                                input_ids=model_input_ids, max_new_tokens=max_new_tokens, do_sample=True, top_p=top_p,
                                temperature=temperature, repetition_penalty=repetition_penalty, eos_token_id=tokenizer.eos_token_id
                            )
                        model_input_ids_len = model_input_ids.size(1)
                        response_ids = outputs[:, model_input_ids_len:]
                        history_token_ids = torch.concat((history_token_ids, response_ids.cpu()), dim=1)
                        response = tokenizer.batch_decode(response_ids)

                        assistant=response[0].strip().replace(tokenizer.eos_token, "")
                        print("Firefly：" + assistant)
                    elif key == "assistant":
                        res.append({"Predictive":assistant,"Realistic=":val.get(key)})
            output_file.write(json.dumps({index:res}, ensure_ascii=False) + "\n")
            print(index)
            if index==200:
                break


if __name__ == '__main__':
    input_file = "/home/zhumx/code/Firefly-master/data/tibetan_data.json"
    output_file=open("/home/zhumx/code/Firefly-master/predictive_llama7b_llama2-chat.json",'w',encoding="utf-8")
    main(input_file)