# Recorded Greetings

Smart Office can play a recorded morning greeting once per employee per day.

## Recommended Setup

Use one full WAV file per employee in:

- `audio/greetings/full/<employee_name>.wav`

Example:

- `audio/greetings/full/Akramov.wav`
- `audio/greetings/full/Baxtiyor_Nigmatjon_ogli.wav`

## Alternative Setup

You can also use 3-part playback:

- `audio/greetings/common/intro.wav`
- `audio/greetings/names/<employee_name>.wav`
- `audio/greetings/common/outro.wav`

Example spoken sequence:

1. `intro.wav` -> "Хуш келибсиз"
2. `<employee_name>.wav` -> "Бахтиёр Нигматжон ўғли"
3. `outro.wav` -> "Кунингиз хайрли ўтсин"

## Name Mapping

If the database employee name does not match the WAV filename, create:

- `audio/greetings/name_map.json`

Example:

```json
{
  "Akramov": "Bah_tiyor_Nigmatjon_ogli",
  "Bekmurodov": "Bekmurodov_full"
}
```

## Audio Format

- Format: `.wav`
- Sample rate: `22050` or `44100`
- Mono is enough
- Keep files short and clean

## Behavior

- Plays only in morning hours
- Plays once per employee per day
- Runs in a separate worker so face recognition is not blocked
