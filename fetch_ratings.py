if results and len(results) > 0:
    result = results[0]
    rating = round(result["rating"] / 10, 1) if "rating" in result else None
    
    # Get cover image
    cover_url = None
    if "cover" in result:
        cover_id = result["cover"]
        cover_response = requests.post(
            "https://api.igdb.com/v4/covers",
            headers=headers,
            data=f'fields url; where id = {cover_id};'
        )
        cover_data = cover_response.json()
        if cover_data:
            cover_url = "https:" + cover_data[0]["url"].replace("t_thumb", "t_cover_big")
        time.sleep(0.25)

    description = result.get("summary", None)

    collection.update_one(
        {"_id": game["_id"]},
        {"$set": {
            "rating": rating,
            "cover": cover_url,
            "description": description
        }}
    )