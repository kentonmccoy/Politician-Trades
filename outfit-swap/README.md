# Outfit Swap

Upload a photo of a person and change what they're wearing. A yellow dress is picked by default, and you can switch to or combine other items like a white top and blue jeans, or type your own (for example, "red leather jacket").

## Run it
1. Install Python 3.10+ from python.org. There's nothing to `pip install`.
2. Get an OpenAI API key at platform.openai.com. Image edits cost a few cents each.
3. In a terminal inside this `outfit-swap` folder:
   - Mac/Linux: `export OPENAI_API_KEY=your-key` then `python server.py`
   - Windows: `set OPENAI_API_KEY=your-key` then `python server.py`
4. Open http://localhost:8001

## Using it
- Click the box (or drag a photo onto it) to upload a JPG or PNG.
- Pick clothes. A dress replaces the top and bottom. Tops, bottoms and jackets can be combined.
- Click **Change outfit**. It takes about 30–60 seconds.
- **Keep editing this one** uses the result as the new starting photo, so you can make one change after another.
- **Download** saves the result.

## Settings (optional environment variables)
- `OUTFIT_QUALITY`: `low`, `medium` (default) or `high`. Higher looks better but costs more.
- `OUTFIT_MODEL`: the OpenAI image model (default `gpt-image-1`).
- `PORT`: the port to use (default 8001).

## Notes
- Only use photos of people who have agreed to it.
- The app only produces normal, fully clothed outfits. It refuses requests to remove or reduce clothing.
- The AI keeps the face, pose and background, but small details can still change.
- Photos go to OpenAI for processing. Nothing is saved on your computer unless you click Download.
