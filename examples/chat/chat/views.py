from django.shortcuts import render

import sockjs


async def chat(request):
    return render(request, "chat.html")


async def chat_msg_handler(msg, session):
    if session.manager is None:
        return

    if msg.type == sockjs.MSG_OPEN:
        session.manager.broadcast("Someone joined.")
    elif msg.type == sockjs.MSG_MESSAGE:
        session.manager.broadcast(msg.data)
    elif msg.type == sockjs.MSG_CLOSED:
        session.manager.broadcast("Someone left.")
