# UnderControlApi
Custom web API to bring together various home control APIs.

# Setup

1. Create a virtual environment
2. `pip install -r requirements.txt`
3. Copy `config.example.toml` to `config.toml` and update with any of your own settings.
4. Run the server using `python main.py`.

# Adapters

To make integration with multiple 3rd party APIs easier, the application auto-registers "Adapter' classes,
that are stored in the `adapters` directory.

TODO: More info, for now see python docstrings.