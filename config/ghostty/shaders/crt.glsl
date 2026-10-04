// Лёгкий ЭЛТ: свечение ярких символов, сканлайны, виньетка. Без искажения геометрии,
// чтобы текст оставался чётким.
void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = fragCoord / iResolution.xy;
    vec4 base = texture(iChannel0, uv);
    vec2 px = 1.0 / iResolution.xy;

    // свечение: только то, что ярче порога (зелёный текст, курсор)
    vec3 glow = vec3(0.0);
    for (int x = -2; x <= 2; x++) {
        for (int y = -2; y <= 2; y++) {
            vec3 s = texture(iChannel0, uv + vec2(float(x), float(y)) * px * 1.6).rgb;
            glow += max(s - 0.82, 0.0);
        }
    }
    glow /= 25.0;

    vec3 col = base.rgb + glow * 1.4;
    col *= 0.95 + 0.05 * sin(fragCoord.y * 3.14159);   // сканлайны через строку пикселей
    vec2 v = uv * (1.0 - uv.yx);
    col *= pow(clamp(v.x * v.y * 16.0, 0.0, 1.0), 0.10); // мягкое затемнение углов
    fragColor = vec4(col, base.a);
}
