def render_job_html(job):
    """Render HTML for a single job (simple or composite)"""
    repository_name = job.repository.name if job.repository else "Unknown"
    
    # Status styling
    if job.status == "completed":
        status_class = "bg-green-100 text-green-800"
        status_icon = "✓"
    elif job.status == "failed":
        status_class = "bg-red-100 text-red-800"
        status_icon = "✗"
    elif job.status == "running":
        status_class = "bg-blue-100 text-blue-800"
        status_icon = "⟳"
    else:
        status_class = "bg-gray-100 text-gray-800"
        status_icon = "◦"
    
    # Format dates
    started_at = job.started_at.strftime("%Y-%m-%d %H:%M") if job.started_at else "N/A"
    finished_at = job.finished_at.strftime("%Y-%m-%d %H:%M") if job.finished_at else "N/A"
    
    # Check if this is a composite job
    is_composite = job.job_type == "composite" and job.tasks
    
    # Job header
    job_title = f"{job.type.replace('_', ' ').title()} - {repository_name}"
    if is_composite:
        progress_text = f"({job.completed_tasks}/{job.total_tasks} tasks)"
        job_title += f" {progress_text}"
    
    html = f'''
        <div class="border rounded-lg bg-white">
            <div class="p-4 hover:bg-gray-50 cursor-pointer" onclick="toggleJobDetails({job.id})">
                <div class="flex items-center justify-between">
                    <div class="flex-1">
                        <div class="flex items-center space-x-3">
                            <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium {status_class}">
                                {status_icon} {job.status.title()}
                            </span>
                            <span class="text-sm font-medium text-gray-900">
                                {job_title}
                            </span>
                        </div>
                        <div class="mt-2 text-xs text-gray-500 space-x-4">
                            <span>Started: {started_at}</span>
                            {f'<span>Finished: {finished_at}</span>' if job.finished_at else ''}
                            {f'<span class="text-red-600">Error: {job.error}</span>' if job.error else ''}
                        </div>
                    </div>
                    <div class="flex-shrink-0 flex items-center space-x-2">
                        <span class="text-sm text-gray-500">#{job.id}</span>
                        <svg id="chevron-{job.id}" class="w-4 h-4 text-gray-400 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                        </svg>
                    </div>
                </div>
            </div>
            <div id="job-details-{job.id}" class="hidden border-t bg-gray-50 p-4">
                <div class="space-y-3">
                    <div class="grid grid-cols-2 gap-4 text-sm">
                        <div>
                            <span class="font-medium text-gray-700">Type:</span>
                            <span class="ml-2 text-gray-900">{job.type}</span>
                        </div>
                        <div>
                            <span class="font-medium text-gray-700">Repository:</span>
                            <span class="ml-2 text-gray-900">{repository_name}</span>
                        </div>
                        <div>
                            <span class="font-medium text-gray-700">Started:</span>
                            <span class="ml-2 text-gray-900">{started_at}</span>
                        </div>
                        <div>
                            <span class="font-medium text-gray-700">Finished:</span>
                            <span class="ml-2 text-gray-900">{finished_at if job.finished_at else "N/A"}</span>
                        </div>
                    </div>
    '''
    
    if is_composite:
        # Render composite job with tasks
        html += f'''
                    <div class="mt-4">
                        <h4 class="text-sm font-medium text-gray-900 mb-3">Tasks:</h4>
                        <div class="space-y-2">
        '''
        
        # Sort tasks by order
        sorted_tasks = sorted(job.tasks, key=lambda t: t.task_order)
        
        for task in sorted_tasks:
            # Task status styling
            if task.status == "completed":
                task_status_class = "bg-green-100 text-green-800"
                task_status_icon = "✓"
            elif task.status == "failed":
                task_status_class = "bg-red-100 text-red-800"
                task_status_icon = "✗"
            elif task.status == "running":
                task_status_class = "bg-blue-100 text-blue-800"
                task_status_icon = "⟳"
            elif task.status == "skipped":
                task_status_class = "bg-yellow-100 text-yellow-800"
                task_status_icon = "⤴"
            else:
                task_status_class = "bg-gray-100 text-gray-800"
                task_status_icon = "◦"
            
            # Task timing
            task_started = task.started_at.strftime("%H:%M:%S") if task.started_at else "N/A"
            task_finished = task.completed_at.strftime("%H:%M:%S") if task.completed_at else "N/A"
            
            # Task duration
            task_duration = ""
            if task.started_at and task.completed_at:
                duration = task.completed_at - task.started_at
                task_duration = f"({duration.total_seconds():.1f}s)"
            
            html += f'''
                            <div class="border rounded p-3 bg-white">
                                <div class="flex items-center justify-between cursor-pointer" onclick="toggleTaskDetails({job.id}, {task.task_order})">
                                    <div class="flex items-center space-x-3">
                                        <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium {task_status_class}">
                                            {task_status_icon} {task.status.title()}
                                        </span>
                                        <span class="text-sm font-medium text-gray-900">{task.task_name}</span>
                                        <span class="text-xs text-gray-500">{task_duration}</span>
                                    </div>
                                    <div class="flex items-center space-x-2">
                                        <span class="text-xs text-gray-500">{task_started} - {task_finished}</span>
                                        <svg id="task-chevron-{job.id}-{task.task_order}" class="w-3 h-3 text-gray-400 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                                        </svg>
                                    </div>
                                </div>
            '''
            
            # Task output section
            if task.output and task.output.strip():
                escaped_output = task.output.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                html += f'''
                                <div id="task-details-{job.id}-{task.task_order}" class="hidden mt-3 pt-3 border-t">
                                    <div class="flex items-center justify-between mb-2">
                                        <h5 class="text-xs font-medium text-gray-700">Output:</h5>
                                        <button onclick="copyTaskOutput({job.id}, {task.task_order})" class="text-xs text-blue-600 hover:text-blue-800">Copy</button>
                                    </div>
                                    <div class="bg-gray-900 text-green-400 p-3 rounded text-xs font-mono whitespace-pre-wrap overflow-x-auto max-h-60 overflow-y-auto" id="task-output-{job.id}-{task.task_order}">{escaped_output}</div>
                                    {f'<div class="mt-2 text-xs text-red-600">Error: {task.error}</div>' if task.error else ''}
                                </div>
                '''
            elif task.error:
                html += f'''
                                <div id="task-details-{job.id}-{task.task_order}" class="hidden mt-3 pt-3 border-t">
                                    <div class="text-xs text-red-600">Error: {task.error}</div>
                                </div>
                '''
            else:
                html += f'''
                                <div id="task-details-{job.id}-{task.task_order}" class="hidden mt-3 pt-3 border-t">
                                    <div class="text-xs text-gray-500">No output available</div>
                                </div>
                '''
            
            html += '''
                            </div>
            '''
        
        html += '''
                        </div>
                    </div>
        '''
    
    else:
        # Render simple job with single output
        has_output = bool(job.log_output and job.log_output.strip())
        if has_output:
            escaped_output = job.log_output.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            html += f'''
                    <div class="mt-4">
                        <div class="flex items-center justify-between mb-2">
                            <h4 class="text-sm font-medium text-gray-900">Output:</h4>
                            <button onclick="copyJobOutput({job.id})" class="text-sm text-blue-600 hover:text-blue-800">Copy</button>
                        </div>
                        <div class="bg-gray-900 text-green-400 p-3 rounded text-xs font-mono whitespace-pre-wrap overflow-x-auto max-h-60 overflow-y-auto" id="job-output-{job.id}">{escaped_output}</div>
                    </div>
            '''
    
    html += '''
                </div>
            </div>
        </div>
    '''
    
    return html