def test_3d_fft():
    coeff_thr = 1e-3
    ncontours = 20

    npoints = 100
    rmax    = 1.0
    rmin    = 0.0

    fig = plt.figure(figsize=(4, 4), dpi=200, constrained_layout=True)
    spec = gridspec.GridSpec(ncols=1, nrows=1, figure=fig)
    axft = fig.add_subplot(spec[0, 0])

    cart_grid = np.linspace(-1.0 * rmax, rmax, npoints, endpoint=True, dtype=float)

    x3d, y3d, z3d = np.meshgrid(cart_grid, cart_grid, cart_grid)

    val = np.zeros((len(x3d),len(y3d),len(z3d)), dtype = complex)
    
    start_time = time.time()

    for i in range(len(cart_grid)):
        for j in range(len(cart_grid)):
            val[i,j,:] =  np.sin(x3d[i,j,:]) * np.cos(y3d[i,j,:]) * np.cos(z3d[i,j,:])

    end_time = time.time()
    print("The time calculation of wavefunction on 3-D cubic grid: " + str("%10.3f"%(end_time-start_time)) + "s")

    start_time = time.time()
    ftval = fftn(val)
    end_time = time.time()
    print("The time calculation 3D Fourier transform: " + str("%10.3f"%(end_time-start_time)) + "s")

    print(np.shape(ftval))

    ft_grid = np.linspace(-1.0/(rmax), 1.0/(rmax), npoints, endpoint=True, dtype=float)

    yftgrid, zftgrid = np.meshgrid(ft_grid,ft_grid)

    line_ft = axft.contourf(yftgrid, zftgrid , ftval[50,:npoints,:npoints].real/np.max(np.abs(ftval)), 
                                        ncontours, cmap = 'jet', vmin=-0.2, vmax=0.2) #vmin=0.0, vmax=1.0cmap = jet, gnuplot, gnuplot2
    plt.colorbar(line_ft, ax=axft, aspect=30)
    
    #axradang_r.set_yticklabels(list(str(np.linspace(rmin,rmax,5.0)))) # set radial tick label
    plt.legend()   
    plt.show()  

