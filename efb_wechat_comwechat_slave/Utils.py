import logging
import tempfile
import threading
import requests as requests
import re
import json
import yaml
from typing import Dict , Any
import pilk
import pydub
import os

#从本地读取配置
def load_config(path : str) -> Dict[str, None]:
    """
    Load configuration from path specified by the framework.
    Configuration file is in YAML format.
    """
    if not os.path.exists(path):
        return
    with open( path , "rb") as f:
        d = yaml.full_load(f)
        if not d:
            return
        config: Dict[str, Any] = d
    return config

def download_file(url: str, retry: int = 3) -> tempfile:
    """
    A function that downloads files from given URL
    Remember to close the file once you are done with the file!
    :param retry: The max retries before giving up
    :param url: The URL that points to the file
    """
    count = 1
    while True:
        try:
            file = tempfile.NamedTemporaryFile()
            r = requests.get(
                url,
                stream=True,
                timeout=30,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/131.0 Safari/537.36 "
                        "MicroMessenger/3.9.12"
                    ),
                    "Referer": "https://weixin.qq.com/",
                },
            )
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    file.write(chunk)
                    file.flush()
            if file.tell() == 0:
                raise ValueError("Downloaded file is empty")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Error occurred when downloading {url}. {e}")
            if count >= retry:
                logging.getLogger(__name__).warning(f"Maximum retry reached. Giving up.")
                raise e
            count += 1
        else:
            break
    return file

def wechatimagedecode( file : str) -> tempfile:
    """
    代码来源 https://github.com/zhangxiaoyang/WechatImageDecoder
    """
    def do_magic(header_code, buf):
        return header_code ^ list(buf)[0] if buf else 0x00
    
    def decode(magic, buf):
        return bytearray([b ^ magic for b in list(buf)])

    def guess_encoding(buf):
        headers = {
            'jpg': (0xff, 0xd8),
            'png': (0x89, 0x50),
            'gif': (0x47, 0x49),
        }
        for encoding in headers:
            header_code, check_code = headers[encoding] 
            magic = do_magic(header_code, buf)
            _, code = decode(magic, buf[:2])
            if check_code == code:
                return (encoding, magic)
        return None

    with open(file , 'rb') as f:
        buf = bytearray(f.read())
    file_type, magic = guess_encoding(buf)

    ret_file = tempfile.NamedTemporaryFile()
    with open(ret_file.name , 'wb') as f:
        f.write(decode(magic, buf))
    f.close()
    return ret_file

def load_local_file_to_temp(file : str) -> tempfile:
    """
    从本地文件读取文件到临时文件
    """
    ret_file = tempfile.NamedTemporaryFile()
    with open(file , 'rb') as f:
        ret_file.write(f.read())
    f.close()
    return ret_file

def load_temp_file_to_local(file : tempfile , path : str) -> None:
    """
    从临时文件写到本地
    """
    with open(path , 'wb') as f:
        f.write(file.read())
    f.close()

def convert_silk_to_mp3(file : tempfile) -> tempfile:
    """
    将silk文件转换为mp3文件
    """
    f = tempfile.NamedTemporaryFile()
    file.seek(0)
    silk_header = file.read(10)
    file.seek(0)
    if b"#!SILK_V3" in silk_header:
        pilk.decode(file.name, f.name)
        file.close()
        pydub.AudioSegment.from_raw(file= f , sample_width=2, frame_rate=24000, channels=1) \
            .export( f , format="ogg", codec="libopus",
                    parameters=['-vbr', 'on'])
    return f


WC_EMOTICON_CONVERSION = {
    '[微笑]': '😃', '[Smile]': '😃',
    '[撇嘴]': '😖', '[Grimace]': '😖',
    '[色]': '😍', '[Drool]': '😍',
    '[发呆]': '😳', '[Scowl]': '😳',
    '[得意]': '😎', '[Chill]': '😎',
    '[流泪]': '😭', '[Sob]': '😭',
    '[害羞]': '☺️', '[Shy]': '☺️','[Blush]': '☺️',
    '[闭嘴]': '🤐', '[Shutup]': '🤐',
    '[睡]': '😴', '[Sleep]': '😴',
    '[大哭]': '😣', '[Cry]': '😣',
    '[尴尬]': '😰', '[Awkward]': '😰',
    '[发怒]': '😡', '[Pout]': '😡',
    '[调皮]': '😜', '[Wink]': '😜',
    '[呲牙]': '😁', '[Grin]': '😁',
    '[惊讶]': '😱', '[Surprised]': '😱',
    '[难过]': '🙁', '[Frown]': '🙁',
    '[囧]': '☺️', '[Tension]': '☺️',
    '[抓狂]': '😫', '[Scream]': '😫',
    '[吐]': '🤢', '[Puke]': '🤢',
    '[偷笑]': '🙈', '[Chuckle]': '🙈',
    '[愉快]': '☺️', '[Joyful]': '☺️',
    '[白眼]': '🙄', '[Slight]': '🙄',
    '[傲慢]': '😕', '[Smug]': '😕',
    '[困]': '😪', '[Drowsy]': '😪',
    '[惊恐]': '😱', '[Panic]': '😱',
    '[流汗]': '😓', '[Sweat]': '😓',
    '[憨笑]': '😄', '[Laugh]': '😄',
    '[悠闲]': '😏', '[Loafer]': '😏',
    '[奋斗]': '💪', '[Strive]': '💪',
    '[咒骂]': '😤', '[Scold]': '😤',
    '[疑问]': '❓', '[Doubt]': '❓',
    '[嘘]': '🤐', '[Shhh]': '🤐',
    '[晕]': '😲', '[Dizzy]': '😲',
    '[衰]': '😳', '[BadLuck]': '😳',
    '[骷髅]': '💀', '[Skull]': '💀',
    '[敲打]': '👊', '[Hammer]': '👊',
    '[再见]': '🙋\u200d♂', '[Bye]': '🙋\u200d♂',
    '[擦汗]': '😥', '[Relief]': '😥',
    '[抠鼻]': '🤷\u200d♂', '[DigNose]': '🤷\u200d♂',
    '[鼓掌]': '👏', '[Clap]': '👏',
    '[坏笑]': '👻','[壞笑]': '👻', '[Trick]': '👻',
    '[左哼哼]': '😾', '[Bah！L]': '😾', 
    '[右哼哼]': '😾', '[Bah！R]': '😾',
    '[哈欠]': '😪', '[Yawn]': '😪',
    '[鄙视]': '😒', '[Lookdown]': '😒',
    '[委屈]': '😣', '[Wronged]': '😣',
    '[快哭了]': '😔', '[Puling]': '😔',
    '[阴险]': '😈', '[Sly]': '😈',
    '[亲亲]': '😘', '[Kiss]': '😘',
    '[可怜]': '😻', '[Whimper]': '😻',
    '[菜刀]': '🔪', '[Cleaver]': '🔪',
    '[西瓜]': '🍉', '[Melon]': '🍉',
    '[啤酒]': '🍺', '[Beer]': '🍺',
    '[咖啡]': '☕', '[Coffee]': '☕',
    '[猪头]': '🐷', '[Pig]': '🐷',
    '[玫瑰]': '🌹', '[Rose]': '🌹',
    '[凋谢]': '🥀', '[Wilt]': '🥀',
    '[嘴唇]': '💋', '[Lip]': '💋',
    '[爱心]': '❤️', '[Heart]': '❤️',
    '[心碎]': '💔', '[BrokenHeart]': '💔',
    '[蛋糕]': '🎂', '[Cake]': '🎂',
    '[炸弹]': '💣', '[Bomb]': '💣',
    '[便便]': '💩', '[Poop]': '💩',
    '[月亮]': '🌃', '[Moon]': '🌃',
    '[太阳]': '🌞', '[Sun]': '🌞',
    '[拥抱]': '🤗', '[Hug]': '🤗',
    '[强]': '👍', '[Strong]': '👍', '[ThumbsUp]': '👍',
    '[弱]': '👎', '[Weak]': '👎', '[ThumbsDown]': '👎',
    '[握手]': '🤝', '[Shake]': '🤝',
    '[胜利]': '✌️', '[Victory]': '✌️',
    '[抱拳]': '🙏', '[Salute]': '🙏',
    '[勾引]': '💁\u200d♂', '[Beckon]': '💁\u200d♂',
    '[拳头]': '👊', '[Fist]': '👊',
    '[OK]': '👌',
    '[跳跳]': '💃', '[Waddle]': '💃',
    '[发抖]': '🙇', '[Tremble]': '🙇',
    '[怄火]': '😡', '[Aaagh!]': '😡',
    '[转圈]': '🕺', '[Twirl]': '🕺',
    '[嘿哈]': '🤣', '[Hey]': '🤣',
    '[捂脸]': '🤦\u200d♂', '[Facepalm]': '🤦\u200d♂',
    '[奸笑]': '😜', '[Smirk]': '😜',
    '[机智]': '🤓', '[Smart]': '🤓',
    '[皱眉]': '😟', '[Concerned]': '😟',
    '[耶]': '✌️', '[Yeah!]': '✌️',
    '[红包]': '🧧', '[Packet]': '🧧',
    '[鸡]': '🐥', '[Chick]': '🐥',
    '[蜡烛]': '🕯️', '[Candle]': '🕯️',
    '[糗大了]': '😥',
    '[Thumbs Up]': '👍', '[Pleased]': '😊',
    '[Rich]': '🀅',
    '[Pup]': '🐶',
    '[吃瓜]': '🙄\u200d🍉','[Onlooker]': '🙄\u200d🍉',
    '[加油]': '💪\u200d😁', '[GoForIt]':  '💪\u200d😁',
    '[加油加油]': '💪\u200d😷',
    '[汗]': '😓', '[Sweats]' : '😓', 
    '[天啊]': '😱', '[OMG]' :'😱', 
    '[一言難盡]': '🤔', '[Emm]': '🤔',
    '[社会社会]': '😏', '[Respect]': '😏', 
    '[旺柴]': '🐶', '[Doge]': '🐶', 
    '[Awesome]': '🐶\u200d😏', 
    '[好的]': '😏\u200d👌', '[NoProb]': '😏\u200d👌', 
    '[哇]': '🤩','[Wow]': '🤩',
    '[打脸]': '😟\u200d🤚', '[MyBad]': '😟\u200d🤚', 
    '[破涕为笑]': '😂', '[破涕為笑]': '😂','[Lol]': '😂',
    '[苦涩]': '😭', '[Hurt]': '😭', 
    '[翻白眼]': '🙄', '[Boring]': '🙄', 
    '[爆竹]': '🧨', '[Firecracker]': '🧨',  
    '[烟花]': '🎆', '[Fireworks]': '🎆', 
    '[裂开]': '💔', '[Broken]' : '💔',
    '[福]': '🧧', '[Blessing]': '🧧', 
    '[發]': '🀅',
    '[礼物]': '🎁', '[Gift]': '🎁', 
    '[庆祝]': '🎉', '[Party]': '🎉',
    '[合十]': '🙏', '[Worship]' : '🙏',
    '[叹气]': '😮‍💨','[Sigh]': '😮‍💨',
    '[让我看看]': '👀', '[LetMeSee]': '👀', 
    '[666]': '6️⃣6️⃣6️⃣',
    '[无语]': '😑', '[Duh]': '😑', 
    '[失望]': '😞', '[Let Down]': '😞', 
    '[恐惧]': '😨', '[Terror]': '😨', 
    '[脸红]': '😳', '[Flushed]': '😳', 
    '[生病]': '😷', '[Sick]': '😷',
    '[笑脸]': '😁', '[Happy]': '😁',
}
