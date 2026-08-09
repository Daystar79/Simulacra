using System;
using System.Threading;

namespace CharacterSimulator.Logic.ProcessExecution;

/// <summary>
/// Circuit breaker pattern implementation to prevent cascading failures
/// when external services (like LLM clients) are down.
/// </summary>
public class CircuitBreaker
{
    private readonly int _failureThreshold;
    private readonly TimeSpan _resetTimeout;
    
    private int _failureCount = 0;
    private DateTime _lastFailureTime = DateTime.MinValue;
    private bool _isOpen = false;
    private readonly object _lock = new object();
    
    /// <summary>
    /// Creates a new CircuitBreaker
    /// </summary>
    /// <param name="failureThreshold">Number of consecutive failures before opening the circuit</param>
    /// <param name="resetTimeout">Time to wait before attempting to reset the circuit</param>
    public CircuitBreaker(int failureThreshold = 5, TimeSpan? resetTimeout = null)
    {
        _failureThreshold = Math.Max(1, failureThreshold);
        _resetTimeout = resetTimeout ?? TimeSpan.FromMinutes(1);
    }
    
    /// <summary>
    /// Gets whether the circuit is currently open (not allowing requests)
    /// </summary>
    public bool IsOpen => _isOpen;
    
    /// <summary>
    /// Gets the current failure count
    /// </summary>
    public int FailureCount => _failureCount;
    
    /// <summary>
    /// Gets the time when the circuit was last tripped
    /// </summary>
    public DateTime LastFailureTime => _lastFailureTime;
    
    /// <summary>
    /// Gets the time remaining until the circuit can be reset (if open)
    /// </summary>
    public TimeSpan TimeUntilReset
    {
        get
        {
            if (!_isOpen) return TimeSpan.Zero;
            var elapsed = DateTime.UtcNow - _lastFailureTime;
            return _resetTimeout > elapsed ? _resetTimeout - elapsed : TimeSpan.Zero;
        }
    }
    
    /// <summary>
    /// Checks if a request can be made (circuit is not open)
    /// </summary>
    /// <returns>True if the request can proceed, false if circuit is open</returns>
    public bool CanExecute()
    {
        if (!_isOpen) return true;
        
        // Auto-reset if timeout has passed
        if (DateTime.UtcNow - _lastFailureTime > _resetTimeout)
        {
            Reset();
            return true;
        }
        
        return false;
    }
    
    /// <summary>
    /// Records a successful operation, resetting the failure count
    /// </summary>
    public void RecordSuccess()
    {
        lock (_lock)
        {
            _failureCount = 0;
            _isOpen = false;
        }
    }
    
    /// <summary>
    /// Records a failure. If threshold is reached, opens the circuit.
    /// </summary>
    public void RecordFailure()
    {
        lock (_lock)
        {
            _failureCount++;
            _lastFailureTime = DateTime.UtcNow;
            
            if (_failureCount >= _failureThreshold)
            {
                _isOpen = true;
            }
        }
    }
    
    /// <summary>
    /// Manually resets the circuit breaker
    /// </summary>
    public void Reset()
    {
        lock (_lock)
        {
            _failureCount = 0;
            _isOpen = false;
            _lastFailureTime = DateTime.MinValue;
        }
    }
    
    /// <summary>
    /// Executes an action with circuit breaker protection
    /// </summary>
    /// <typeparam name="TResult">Result type</typeparam>
    /// <param name="action">The action to execute</param>
    /// <param name="fallback">Fallback value if circuit is open</param>
    /// <returns>The result of the action, or fallback if circuit is open</returns>
    public TResult Execute<TResult>(Func<TResult> action, TResult fallback)
    {
        if (!CanExecute())
            return fallback;
        
        try
        {
            var result = action();
            RecordSuccess();
            return result;
        }
        catch
        {
            RecordFailure();
            throw;
        }
    }
    
    /// <summary>
    /// Executes an async action with circuit breaker protection
    /// </summary>
    /// <typeparam name="TResult">Result type</typeparam>
    /// <param name="action">The async action to execute</param>
    /// <param name="fallback">Fallback value if circuit is open</param>
    /// <returns>The result of the action, or fallback if circuit is open</returns>
    public async System.Threading.Tasks.Task<TResult> ExecuteAsync<TResult>(
        Func<CancellationToken, System.Threading.Tasks.Task<TResult>> action,
        TResult fallback,
        CancellationToken ct = default)
    {
        if (!CanExecute())
            return fallback;
        
        try
        {
            var result = await action(ct).ConfigureAwait(false);
            RecordSuccess();
            return result;
        }
        catch
        {
            RecordFailure();
            throw;
        }
    }
}
