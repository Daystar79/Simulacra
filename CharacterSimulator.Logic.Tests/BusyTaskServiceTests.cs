using System;
using CharacterSimulator.Logic.Services;
using Xunit;

namespace CharacterSimulator.Logic.Tests;

[Collection("StaticStateTests")]
public class BusyTaskServiceTests
{
    [Fact]
    public void BeginTask_TracksActiveTaskAndFiresEvent()
    {
        BusyTaskService.ClearAll();
        bool eventFired = false;
        BusyTaskService.OnTaskStateChanged += () => eventFired = true;

        Assert.False(BusyTaskService.IsBusy);

        using (var token = BusyTaskService.BeginTask("test_task_1", "Thinking about test operation..."))
        {
            Assert.True(BusyTaskService.IsBusy);
            Assert.Equal("Thinking about test operation...", BusyTaskService.ActiveTaskText);
            Assert.True(eventFired);
        }

        Assert.False(BusyTaskService.IsBusy);
        Assert.Equal("", BusyTaskService.ActiveTaskText);
    }
}
