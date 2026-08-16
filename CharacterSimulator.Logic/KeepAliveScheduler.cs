using System;
using System.Threading;
using System.Threading.Tasks;

namespace CharacterSimulator.Logic;

/// <summary>
/// One-shot idle timer. <see cref="Arm"/> starts (or restarts) a delay;
/// <see cref="Cancel"/> aborts it. Fire always yields off the Arm() stack
/// so a zero-delay test hook cannot recurse into the turn loop.
/// </summary>
public sealed class KeepAliveScheduler : IDisposable
{
    private readonly Func<TimeSpan> _nextDelay;
    private readonly Action _onFire;
    private readonly Func<TimeSpan, CancellationToken, Task> _delayAsync;
    private readonly object _gate = new();
    private CancellationTokenSource? _cts;

    public KeepAliveScheduler(
        Func<TimeSpan> nextDelay,
        Action onFire,
        Func<TimeSpan, CancellationToken, Task>? delayAsync = null)
    {
        _nextDelay = nextDelay ?? throw new ArgumentNullException(nameof(nextDelay));
        _onFire = onFire ?? throw new ArgumentNullException(nameof(onFire));
        _delayAsync = delayAsync ?? DefaultDelayAsync;
    }

    public bool IsArmed
    {
        get { lock (_gate) return _cts != null; }
    }

    public void Arm()
    {
        CancellationTokenSource cts;
        TimeSpan delay;
        lock (_gate)
        {
            CancelUnlocked();
            cts = new CancellationTokenSource();
            _cts = cts;
            delay = _nextDelay();
            if (delay < TimeSpan.Zero) delay = TimeSpan.Zero;
        }

        _ = RunAsync(cts, delay);
    }

    public void Cancel()
    {
        lock (_gate) CancelUnlocked();
    }

    public void Dispose() => Cancel();

    private void CancelUnlocked()
    {
        if (_cts == null) return;
        try { _cts.Cancel(); } catch { /* already disposed */ }
        _cts.Dispose();
        _cts = null;
    }

    private async Task RunAsync(CancellationTokenSource cts, TimeSpan delay)
    {
        try
        {
            await Task.Yield();
            if (delay > TimeSpan.Zero)
                await _delayAsync(delay, cts.Token).ConfigureAwait(false);

            lock (_gate)
            {
                if (!ReferenceEquals(_cts, cts)) return;
                _cts.Dispose();
                _cts = null;
            }

            _onFire();
        }
        catch (OperationCanceledException)
        {
            // cancelled — stay quiet
        }
        catch (ObjectDisposedException)
        {
            // CTS disposed by Cancel during await
        }
        catch
        {
            // Timer must never take down the host
        }
    }

    private static Task DefaultDelayAsync(TimeSpan delay, CancellationToken ct) =>
        Task.Delay(delay, ct);
}
