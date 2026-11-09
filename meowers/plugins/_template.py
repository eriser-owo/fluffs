from __future__ import annotations

from fluffs.config import get_active_config
from fluffs.core import EventContext, rules
from fluffs.napcat import message as msg

_cfg = get_active_config()
_prefixes = _cfg.bot.command_prefixes if _cfg else []
command_prefix = (_prefixes or ["//"])[0]

__plugin_meta__ = {
    "name": "template",
    "description": "插件模板",
    "usage": f"只是模板而已。展示了{command_prefix}hello命令、关键词回复和引用回复。本模板由下划线开头，不会被加载",
    "version": "0.1.0",
    "author": "your_name",
}

#食用方法
def setup(bot) -> None:
    #命令
    @bot.on_command("hello")
    async def hello(ctx: EventContext) -> None:
        await ctx.reply("world")
        #说{命令前缀}hello 就回复world

    #任意消息 / 规则组合
    @bot.on_message(rules.all_of(rules.group_only, rules.regex(r"^(?P<name>.+)在吗$")), priority=20)
    async def on_asking(ctx: EventContext) -> None:
        match = ctx.match
        who = match.group("name") if match else "你"
        await ctx.reply(f"{who}，我在")

    #主动发消息，富文本（@+文字+图片）
    @bot.on_command("pic")
    async def send_pic(ctx: EventContext) -> None:
        event = ctx.message_event
        if event is None or not event.is_group:
            return
        await bot.api.send_group_msg(
            event.group_id,
            msg.build(msg.at(event.user_id), " ", "给你一张图：", msg.image("https://example.com/a.png")),
        )

    #引用回复：把某条消息引用起来再回一句
    #方式一：ctx.reply 加 quote=True（引用「当前这条」消息）
    @bot.on_command("引用")
    async def quote_reply(ctx: EventContext) -> None:
        await ctx.reply(ctx.args or "引用回复示例", quote=True)

    #方式二：bot.api.reply_to 引用「任意一条」消息
    #用法：先回复某条消息，再发 {command_prefix}回复 内容
    @bot.on_command("回复")
    async def reply_to(ctx: EventContext) -> None:
        event = ctx.message_event
        if event is None or not event.is_group:
            return
        reply_segs = event.get_segments("reply")
        if not reply_segs:
            await ctx.send(f"先回复某条消息，再发 {command_prefix}回复 内容")
            return
        target_id = int(reply_segs[0]["data"]["id"])
        await bot.api.reply_to(target_id, ctx.args or "这就引用回复喵", group_id=event.group_id)

    #卸载 / 退出时释放资源。没有资源就不用写这个，有资源用 bot.on_teardown 注册，
    # async def teardown(_bot) -> None:
    #     replace with function body
    #     pass
    # bot.on_teardown(teardown)
