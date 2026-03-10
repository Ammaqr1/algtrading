import asyncio

from prisma import Prisma
import os
from dotenv import load_dotenv

load_dotenv()

access_token = os.getenv('access_token')


async def main() -> None:
    db = Prisma()
    await db.connect()

    # post = await db.post.create(
    #     {
    #         'title': 'Hello from prisma!',
    #         'desc': 'Prisma is a database toolkit and makes databases easy.',
    #         'published': True,
    #     }
    # )
    # print(f'created post: {post.model_dump_json(indent=2)}')

    # user = await db.user.create(
    #     {
    #         'name': 'Ammar',
    #         'apiKey': '58f6b253-4d94-4361-8ded-f9d86c020c50',
    #         'apiSecret': '887gq745nf',
    #         'apitoken': os.getenv('access_token'),
    #     }
    # )
    # print(f'created user: {user.model_dump_json(indent=2)}')

    found = await db.post.find_many()
    # print(found,'this is found','\n', type(found), '\n', found[0])
    print(f"Found {len(found)} posts:")
    for post in found:
        print(post.id)
        # print(post.model_dump_json(indent=2).get('id'))

    await db.disconnect()


async def get_user():
    db = Prisma()
    await db.connect()
    found = await db.user.find_many()
    print(f"Found {len(found)} posts:")
    await db.disconnect()
    return found
 

if __name__ == '__main__':
    asyncio.run(main())