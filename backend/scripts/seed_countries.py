"""Compatibility entrypoint: python -m scripts.seed_countries"""

from app.db.seed import main

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
