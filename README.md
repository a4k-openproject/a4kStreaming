<img align="left" width="115px" height="115px" src="icon.png">

# a4kStreaming

<br/>

## Status
![status-api](https://github.com/newt-sc/a4kStreaming/workflows/API/badge.svg)![status-suite](https://github.com/newt-sc/a4kStreaming/workflows/Suite/badge.svg)

## Description

IMDb-based media browser addon for KODI with streaming support via external providers.
Designed for low-end devices and Estuary skin.

## Preview
![usage](https://media.giphy.com/media/IdUqHVT9dxgZ5YEObr/source.gif)

## Features
  * IMDb:
    * Authentication via cookie
    * Browsing for titles
      * Trending
      * Fan Favourites
      * Recommended
      * Discover by Year
    * Browsing Shows
      * Seasons
      * Season episodes
    * Lists
    * Watchlist
    * Search for titles or people
    * Mark as watched/unwatched (by rating/unrating a title)
      * Auto mark as watched when played more than 90 percents
    * Add/Remove to/from list
    * Artwork for posters, thumbnails and fanart
    * Trailers
    * Rate/Unrate titles
  * Provider support
    * Install
    * Manage
    * Auto update
    * Caching of results
  * Debrid support
    * Premiumize
  * Misc
    * Migrate watched titles from Trakt.tv to IMDb (via rating)
    * Migrate movies and shows collection from Trakt.tv to IMDb custom lists

## Installation

Steps to install a4kStreaming:
1. Go to the KODI **File manager**.
2. Click on **Add source**.
3. The path for the source is https://newt-sc.github.io/a4kStreaming/packages/
4. (Optional) Name it **a4kStreaming-repo**.
5. Head to **Addons**.
6. Select **Install from zip file**.
7. When it asks for the location select **a4kStreaming-repo** and install `a4kStreaming-repository.zip`.
8. Go back to **Addons** and select **Install from repository**
9. Select the **a4kStreaming** menu item

## Contribution

Configure hooks for auto update of `addons.xml`:
```sh
git config core.hooksPath .githooks
```
## License

MIT
