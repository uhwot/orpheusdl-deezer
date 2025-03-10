# orpheusdl-deezer
[OrpheusDL](https://github.com/yarrm80s/orpheusdl) module for downloading music from [Deezer](https://www.deezer.com/)

# Getting started
## Prerequisites
- [OrpheusDL](https://github.com/yarrm80s/orpheusdl), duh

## Installation
- Clone the repository from your ```orpheusdl``` directory:\
```git clone https://github.com/uhwot/orpheusdl-deezer modules/deezer```
- Update ```config/settings.json``` with Deezer settings:\
```python orpheus.py```

# Configuration
## Global
```download_quality```:
| Value      | Format              |
| ---------- | ------------------- |
| "hifi"     | 16-bit 44.1kHz FLAC |
| "lossless" | 16-bit 44.1kHz FLAC |
| "high"     | MP3 320kbps         |
| "medium"   | MP3 320kbps         |
| "low"      | MP3 128kbps         |
| "minimum"  | MP3 128kbps         |

```main_resolution```:\
Maxes out at 3000px\
If original cover size is smaller than the one specified, falls back to 1200px

## Deezer
| Setting         | Description                                         |
| --------------- | --------------------------------------------------- |
| `client_id`     | Client ID used for login                            |
| `client_secret` | Client secret used for login                        |
| `bf_secret`     | Constant for deriving key used for track decryption |
| `email`         | Account email                                       |
| `password`      | Account password                                    |
