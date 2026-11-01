(
{
    var size = 5;
    Klank.ar(`[
        Array.rand(size, 220, 4400.00),
        Array.rand(size, 0.5, 1.0),
        Array.rand(size, 0.1, 10)
    ], Dust.ar(1)) ! 2
}.play
)
