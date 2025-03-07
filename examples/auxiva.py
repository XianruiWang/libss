"""Example of blind source separation with auxiliary-function-based independent vector analysis."""
import os

import numpy as np
import pyroomacoustics as pra
from scipy.io import wavfile

import libss
from libss.separation.utils import callback_eval, projection_back


def pcm2float(sig, dtype="float32"):
    """Convert PCM signal to floating point with a range from -1 to 1.
    Use dtype='float32' for single precision.
    Parameters
    ----------
    sig : array_like
        Input array, must have integral type.
    dtype : data type, optional
        Desired (floating point) data type.
    Returns
    -------
    numpy.ndarray
        Normalized floating point data.
    See Also
    --------
    float2pcm, dtype
    """
    sig = np.asarray(sig)
    if sig.dtype.kind not in "iu":
        raise TypeError("'sig' must be an array of integers")
    dtype = np.dtype(dtype)
    if dtype.kind != "f":
        raise TypeError("'dtype' must be a floating point type")

    i = np.iinfo(sig.dtype)
    abs_max = 2 ** (i.bits - 1)
    offset = i.min + abs_max
    return (sig.astype(dtype) - offset) / abs_max


# Read wav file
ref_mic = 1
# n_src = 3
# datadir = os.path.join(".", "examples", "data")
n_src = 2
datadir = os.path.join(".", "examples", "input", "dynamic")
fs = -1
wav_fmt = "src%d_mic%d.wav"

# (n_src, n_mic, n_samples)
premix = [[] for _ in range(n_src)]
for i in range(n_src):
    for j in range(n_src):
        fs, audio = wavfile.read(os.path.join(datadir, wav_fmt % (i, j)))
        premix[i].append(audio)
        if fs < 0:
            raise ValueError("Sampling frequency is not valid.")

premix = np.array(premix)
premix = pcm2float(premix)
mix = premix.sum(axis=0)
ref = premix[:, ref_mic, :]

# STFT
n_fft, hop = 4096, 1024
win_a = np.hamming(n_fft)
win_s = pra.transform.compute_synthesis_window(win_a, hop)
engine = pra.transform.STFT(
    n_fft,
    hop,
    analysis_window=win_a,
    synthesis_window=win_s,
    channels=n_src,
)

mix_tf = engine.analysis(mix.T)

separator = libss.separation.AuxIVA(
    mix_tf,
    update_demix_filter="IP1",
    update_source_model="Gauss",
    ref_mic=0,
)

n_iter = 50
si_sdr, si_sir, si_sar = [], [], []
callback_eval(ref, mix, si_sdr, si_sir, si_sar)

y = []
print(si_sdr[-1])
for it in range(n_iter):
    # print(separator.loss)
    separator.step()

    # Evaluation
    if it % 10 == 0:
        z = projection_back(
            separator.estimated,
            mix_tf,
            ref_mic=ref_mic,
            W=separator.demix_filter,
        )
        # Inverse STFT
        est = pra.transform.synthesis(z, n_fft, hop, win=win_s)[n_fft - hop :, :].T
        m = np.minimum(ref.shape[1], est.shape[1])

        # Evaluate BSS performance
        y = callback_eval(ref[:, :m], est[:, :m], si_sdr, si_sir, si_sar)
        print(si_sdr[-1])

for s in range(n_src):
    wavfile.write(f"./examples/output/est_{s}.wav", fs, y[s])
