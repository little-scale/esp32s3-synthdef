(
{
    var size = 5;
    Klank.ar(`[
        Array.fill(size, { Rand(220, 4400.00) }),
        Array.fill(size, { Rand(0.5, 1.0) }),
        Array.fill(size, { Rand(0.1, 10) })
    ], Dust.ar(1)) ! 2
}.play
)
