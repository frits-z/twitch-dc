# twitch-dc

**⚠ in development**

I developed this package with a specific usecase: Data collection from the Twitch API. Focus is to keep it simple and do it well.


## Getting started

```python
from twitchdc import HelixAPI

helix = HelixAPI('my_client_id', 'my_client_secret')

print(helix.get_top_games(1))
#Returns
[{'id': '509663', 'name': 'Special Events', 'box_art_url': 'https://static-cdn.jtvnw.net/ttv-boxart/509663-{width}x{height}.jpg', 'igdb_id': ''}]
```

An [app access token](https://dev.twitch.tv/docs/authentication/#app-access-tokens) is necessary to make API calls. This package uses the [client credentials grant flow](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#client-credentials-grant-flow). You need to register [here](https://dev.twitch.tv/docs/authentication/register-app/) to get your `client_id` and `client_secret`. 

This package takes care of refreshing your access token. Optionally, upon initialisation of your `HelixAPI` instance, you can pass i) an existing access token, and/or ii) a function that gets called when the access token is refreshed (so you can store it). 


## Other Python wrappers of Twitch API

There are a few other Python wrappers out there (below). I encourage you to check them out, especially if you have a different usecase (e.g. chatbot). They are generally more complete, but also more complex. Everything is an object, which I find undesirable for data collection.
* https://github.com/PetterKraabol/Twitch-Python
* https://github.com/tsifrer/python-twitch-client
* https://github.com/Teekeks/pyTwitchAPI
* https://github.com/TwitchIO/TwitchIO
