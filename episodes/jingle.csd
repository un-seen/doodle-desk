<CsoundSynthesizer>
<CsOptions>
-d -m0
</CsOptions>
<CsInstruments>
; doodle episode jingle: plucked ukulele strums, a bell melody, a soft bass and finger snaps.
; C - Am - F - G - C at 132 BPM, two bars and a ring-out.
sr     = 48000
ksmps  = 16
nchnls = 2
0dbfs  = 1

gaRevL init 0
gaRevR init 0

; plucked string: p4 amp, p5 Hz, p6 pan
instr Uke
  aP     pluck p4, p5, p5, 0, 1
  aP     butlp aP, 4200
  aEnv   linseg 1, p3 - 0.05, 1, 0.05, 0
  aL, aR pan2 aP * aEnv, p6
  outs aL, aR
  gaRevL += aL * 0.18
  gaRevR += aR * 0.18
endin

; bell: three inharmonic partials, p4 amp, p5 Hz
instr Bell
  aE1    expon 1, p3, 0.001
  aE2    expon 1, p3 * 0.5, 0.001
  aS     = poscil(1, p5) * aE1 + poscil(0.4, p5 * 2.76) * aE2 + poscil(0.18, p5 * 5.4) * aE2 * aE2
  aAtk   linseg 0, 0.004, 1, p3 - 0.004, 1
  aS     = aS * aAtk * p4
  outs aS * 0.9, aS
  gaRevL += aS * 0.3
  gaRevR += aS * 0.3
endin

; round bass: p4 amp, p5 Hz
instr Bass
  aEnv   linseg 0, 0.01, 1, p3 * 0.6, 0.5, p3 * 0.4 - 0.01, 0
  aS     = (poscil(1, p5) + poscil(0.3, p5 * 2)) * aEnv * p4
  outs aS, aS
endin

; finger snap: p4 amp
instr Snap
  aN     rand 1
  aN     butbp aN, 2600, 1800
  aEnv   expon 1, p3, 0.001
  outs aN * aEnv * p4, aN * aEnv * p4 * 0.8
  gaRevL += aN * aEnv * p4 * 0.2
  gaRevR += aN * aEnv * p4 * 0.2
endin

instr Master
  aL, aR reverbsc gaRevL, gaRevR, 0.72, 9000
  outs aL, aR
  clear gaRevL, gaRevR
endin
</CsInstruments>
<CsScore>
; one beat = 60/132 = 0.4545 s
; strums: each chord as four quick plucks (G4 C5 E5 A5 shapes)
#define STRUM(T'A'B'C'D) #
i "Uke" $T          1.6 0.32 $A  0.35
i "Uke" [$T+0.018]  1.6 0.30 $B  0.45
i "Uke" [$T+0.036]  1.6 0.28 $C  0.55
i "Uke" [$T+0.054]  1.6 0.26 $D  0.65
#
$STRUM(0.000'392.0'523.3'659.3'880.0)
$STRUM(0.909'440.0'523.3'659.3'880.0)
$STRUM(1.818'440.0'523.3'698.5'880.0)
$STRUM(2.727'392.0'587.3'698.5'987.8)
$STRUM(3.636'392.0'523.3'659.3'1046.5)

; bell melody
i "Bell" 0.000 0.9 0.30 1046.5
i "Bell" 0.227 0.9 0.26 1318.5
i "Bell" 0.454 0.9 0.26 1568.0
i "Bell" 0.909 0.9 0.28 1760.0
i "Bell" 1.136 0.9 0.24 1568.0
i "Bell" 1.363 0.9 0.24 1318.5
i "Bell" 1.818 0.9 0.28 1396.9
i "Bell" 2.045 0.9 0.24 1760.0
i "Bell" 2.727 0.9 0.28 1568.0
i "Bell" 2.954 0.9 0.24 1975.5
i "Bell" 3.181 0.6 0.24 2349.3
i "Bell" 3.636 2.2 0.34 2093.0

; bass on the downbeats
i "Bass" 0.000 0.8 0.40 130.8
i "Bass" 0.909 0.8 0.40 110.0
i "Bass" 1.818 0.8 0.40 87.3
i "Bass" 2.727 0.8 0.40 98.0
i "Bass" 3.636 1.4 0.45 65.4

; snaps on beats 2 and 4
i "Snap" 0.454 0.12 0.35
i "Snap" 1.363 0.12 0.35
i "Snap" 2.272 0.12 0.35
i "Snap" 3.181 0.12 0.35

i "Master" 0 6.2
e
</CsScore>
</CsoundSynthesizer>
